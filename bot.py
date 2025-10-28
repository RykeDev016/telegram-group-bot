import logging
import time
import re
import asyncio
from collections import defaultdict, deque
from datetime import datetime
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, JobQueue
from telegram.error import BadRequest, Forbidden

# config logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# token do seu bot
TOKEN = "TOKEN BURRO"

#estrut armazenamento
user_warnings = defaultdict(int)
user_stickers = defaultdict(lambda: deque(maxlen=5))
user_messages = defaultdict(lambda: deque(maxlen=10))
blacklist = set()
muted_users = {}  # {user_id: timestamp_fim_mute}
admin_cache = {}
user_database = {}  # {user_id: {'username': str, 'first_name': str, 'last_name': str, 'last_seen': timestamp}}
username_to_id = {}  # {username_lower: user_id} - mapeamento rápido de username para ID
welcome_message = "Bem-vindo(a) ao grupo! 👋"
group_settings = defaultdict(lambda: {'welcome_enabled': False, 'antiraid': False, 'locked': False})

# cnfig RATE LIMITES FLOOD
MAX_STICKERS = 5
TIME_WINDOW = 10
MAX_WARNINGS = 3
MAX_MESSAGES = 8
MESSAGE_TIME_WINDOW = 5

# regex para detectar links (nao funcionakkk)
URL_REGEX = re.compile(
    r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\$$\$$,]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
    re.IGNORECASE
)

# emojis interface
EMOJIS = {
    "bot": "🤖",
    "warn": "⚠️",
    "ban": "🚫",
    "kick": "👢",
    "mute": "🔇",
    "unmute": "🔊",
    "unban": "🔓",
    "success": "✅",
    "error": "❌",
    "info": "ℹ️",
    "rules": "📋",
    "user": "👤",
    "admin": "👮",
    "clock": "⏰",
    "stats": "📊",
    "settings": "⚙️",
    "time": "⏱️",
    "reason": "📝",
    "refresh": "🔄",
    "pin": "📌",
    "welcome": "👋",
    "lock": "🔒",
    "unlock": "🔓",
    "promote": "⬆️",
    "demote": "⬇️",
    "unwarn": "✅"
}

async def update_user_database(user):
    """Atualiza o banco de dados de usuários com informações do usuário"""
    if not user or user.is_bot:
        return
    
    user_id = user.id
    username = user.username.lower() if user.username else None
    
    user_database[user_id] = {
        'user_id': user_id,
        'username': username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'last_seen': time.time()
    }
    
    # atualiza  de username para ID
    if username:
        username_to_id[username] = user_id
    
    logger.info(f"Usuário atualizado no banco: {user.first_name} (@{username}) - ID: {user_id}")

async def find_user_by_username(username, update, context):
    """Encontra usuário pelo username usando o banco de dados local - MUITO MAIS CONFIÁVEL"""
    try:
        clean_username = username.lower().replace('@', '')
        
        # Método 1: Busca no banco de dados local (MAIS RÁPIDO E CONFIÁVEL)
        if clean_username in username_to_id:
            user_id = username_to_id[clean_username]
            if user_id in user_database:
                user_data = user_database[user_id]
                logger.info(f"✅ Usuário @{clean_username} encontrado no banco local!")
                
                class UserInfo:
                    def __init__(self, data):
                        self.id = data['user_id']
                        self.username = data['username']
                        self.first_name = data['first_name']
                        self.last_name = data['last_name']
                
                return UserInfo(user_data)
        
        chat_id = update.effective_chat.id
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            for admin in admins:
                if admin.user.username and admin.user.username.lower() == clean_username:
                    await update_user_database(admin.user)
                    logger.info(f"✅ Usuário @{clean_username} encontrado nos admins!")
                    return admin.user
        except Exception as e:
            logger.debug(f"Erro ao buscar admins: {e}")
        
        # isso só funciona se o usuário enviou mensagens recentemente
        logger.info(f"🔍 Tentando buscar @{clean_username} nas mensagens recentes...")
        
        if clean_username.isdigit():
            user_id = int(clean_username)
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                await update_user_database(member.user)
                logger.info(f"✅ Usuário encontrado por ID: {user_id}")
                return member.user
            except Exception as e:
                logger.debug(f"Não encontrou por ID: {e}")
        
        logger.warning(f"❌ Usuário @{clean_username} não encontrado em nenhum método")
        return None
        
    except Exception as e:
        logger.error(f"Erro geral ao buscar usuário @{username}: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start com interface bonita"""
    await update_user_database(update.effective_user)
    
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['rules']} Regras", callback_data="rules")],
        [InlineKeyboardButton(f"{EMOJIS['info']} Comandos", callback_data="commands")],
        [InlineKeyboardButton(f"{EMOJIS['stats']} Estatísticas", callback_data="stats")],
        [InlineKeyboardButton(f"{EMOJIS['refresh']} Atualizar Cache", callback_data="refresh_cache")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
{EMOJIS['bot']} *Bot de Gerenciamento de Grupos - COMPLETO*

✨ *Funcionalidades Ativas:*
• {EMOJIS['ban']} Sistema de banimento e kick
• {EMOJIS['mute']} Silenciamento temporário
• {EMOJIS['warn']} Sistema de advertências
• {EMOJIS['pin']} Fixar/desfixar mensagens
• {EMOJIS['welcome']} Mensagens de boas-vindas
• {EMOJIS['lock']} Proteção anti-raid
• {EMOJIS['user']} Informações de usuários
• {EMOJIS['rules']} Moderação automática

🔧 *Comandos Principais:*
`/ban @user motivo` - Banir permanentemente
`/kick @user motivo` - Expulsar (pode voltar)
`/mute @user 10 motivo` - Silenciar
`/warn @user motivo` - Advertir
`/info @user` - Ver informações
`/pin` - Fixar mensagem (reply)
`/welcome` - Configurar boas-vindas

💡 *DICA IMPORTANTE:*
✅ Use *REPLY* (responder mensagem) para 100% de confiabilidade
✅ O bot agora salva TODOS os usuários automaticamente
✅ Use `/help` para ver todos os comandos
    """
    
    await update.message.reply_text(
        welcome_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /help com todos os comandos disponíveis"""
    await update_user_database(update.effective_user)
    
    help_text = f"""
{EMOJIS['bot']} *LISTA COMPLETA DE COMANDOS*

🔨 *MODERAÇÃO:*
`/ban @user motivo` - Banir permanentemente
`/ban 123456 motivo` - Banir por ID
`/unban @user` - Desbanir usuário
`/kick @user motivo` - Expulsar (pode retornar)
`/mute @user 10 motivo` - Silenciar (minutos)
`/unmute @user` - Dessilenciar
`/warn @user motivo` - Advertir (3 = ban)
`/unwarn @user` - Remover advertência
`/warnings @user` - Ver advertências

📌 *MENSAGENS:*
`/pin` - Fixar mensagem (reply)
`/unpin` - Desfixar mensagem (reply ou todas)
`/purge 10` - Deletar últimas 10 mensagens
`/delete` - Deletar mensagem (reply)

👤 *INFORMAÇÕES:*
`/info @user` - Informações do usuário
`/info 123456` - Info por ID
`/id` - Ver seu ID
`/stats` - Estatísticas do grupo
`/admins` - Lista de administradores

⚙️ *CONFIGURAÇÕES:*
`/welcome on/off` - Ativar boas-vindas
`/setwelcome texto` - Definir mensagem
`/lock` - Bloquear grupo (anti-raid)
`/unlock` - Desbloquear grupo
`/antiraid on/off` - Proteção anti-raid avançada

🔧 *ADMINISTRAÇÃO:*
`/promote @user` - Promover a admin
`/demote @user` - Remover admin
`/refresh` - Atualizar cache
`/rules` - Ver regras do grupo

💡 *DICAS IMPORTANTES:*
✅ *SEMPRE use REPLY quando possível* (100% confiável)
✅ Você pode usar ID numérico: `/ban 123456789 motivo`
✅ O bot salva usuários automaticamente
✅ Admins têm imunidade às regras
✅ Use `/info @user` para ver o ID de alguém

🛡️ *ANTI-RAID:*
O modo anti-raid ativa proteções extras contra spam em massa:
• Monitoramento intensivo de novos membros
• Limites de mensagens mais rígidos
• Banimentos automáticos acelerados
Use `/antiraid on` durante ataques!

⏰ *MENSAGENS DE BOAS-VINDAS:*
São deletadas automaticamente após 1 minuto para manter o grupo limpo!

❓ *Por que não encontra usuários?*
O Telegram não permite buscar usuários que nunca enviaram mensagens. Use REPLY ou peça para a pessoa enviar uma mensagem primeiro!
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /rules com design melhorado"""
    await update_user_database(update.effective_user)
    
    rules_text = f"""
{EMOJIS['rules']} *REGRAS DO GRUPO*

{EMOJIS['ban']} *PROIBIÇÕES:*
• ❌ Enviar links não autorizados
• ❌ Encaminhar mensagens de outros grupos
• ❌ Spam de menções (@)
• ❌ Conteúdo inadequado ou ofensivo
• ❌ Flood de mensagens/figurinhas
• ❌ Comportamento tóxico

{EMOJIS['warn']} *LIMITES:*
• ⚠️ Máximo 5 figurinhas em 10 segundos
• ⚠️ Sistema de 3 advertências = banimento automático
• ⚠️ Máximo 8 mensagens em 5 segundos
• ⚠️ Respeite todos os membros

{EMOJIS['success']} *PERMITIDO:*
• ✅ Mencionar usuários normally
• ✅ Conversas respeitosas
• ✅ Figurinhas com moderação
• ✅ Compartilhar conteúdo relevante

{EMOJIS['admin']} *Administradores têm imunidade às regras automáticas*

Use `/help` para ver todos os comandos disponíveis.
    """
    
    keyboard = [[InlineKeyboardButton(f"{EMOJIS['bot']} Menu", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        rules_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def refresh_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando para limpar e atualizar o cache manualmente"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    admin_cache.clear()
    
    total_users = len(user_database)
    total_usernames = len(username_to_id)
    
    await update.message.reply_text(
        f"{EMOJIS['refresh']} *Cache Atualizado!*\n\n"
        f"📊 *Estatísticas do Banco de Dados:*\n"
        f"• Usuários salvos: {total_users}\n"
        f"• Usernames mapeados: {total_usernames}\n\n"
        f"✅ *O bot conhece {total_users} usuários deste grupo!*",
        parse_mode='Markdown'
    )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /ban com reply ou @username + motivo - CORRIGIDO"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    reason = "Sem motivo especificado"
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
        if context.args:
            reason = " ".join(context.args)
        
        await send_ban_confirmation(update, user_id, user_name, username, reason)
        return
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg if username_arg.startswith('@') else f"ID:{username_arg}"
                if len(context.args) > 1:
                    reason = " ".join(context.args[1:])
                
                await send_ban_confirmation(update, user_id, user_name, username, reason)
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} *Usuário {username_arg} não encontrado!*\n\n"
                    f"*Por que isso acontece?*\n"
                    f"O Telegram não permite que bots busquem usuários que nunca enviaram mensagens no grupo.\n\n"
                    f"*✅ SOLUÇÕES (em ordem de preferência):*\n\n"
                    f"*1. RESPONDER MENSAGEM (100% confiável)*\n"
                    f"   • Responda qualquer mensagem do usuário\n"
                    f"   • Digite: `/ban motivo`\n"
                    f"   • ✅ Funciona SEMPRE!\n\n"
                    f"*2. Pedir para enviar mensagem*\n"
                    f"   • Peça para o usuário enviar UMA mensagem\n"
                    f"   • O bot salvará automaticamente\n"
                    f"   • Depois use: `/ban @user motivo`\n\n"
                    f"*3. Usar ID numérico*\n"
                    f"   • Se souber o ID: `/ban 123456789 motivo`\n"
                    f"   • Para ver ID: peça para usar `/id`\n\n"
                    f"*4. Atualizar cache*\n"
                    f"   • Use `/refresh` e tente novamente\n\n"
                    f"💡 *Dica:* O bot já salvou {len(user_database)} usuários deste grupo!",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso correto:*\n\n"
                f"*Opção 1 (RECOMENDADO):*\n"
                f"Responda uma mensagem com `/ban motivo`\n\n"
                f"*Opção 2:*\n"
                f"`/ban @username motivo`\n\n"
                f"*Opção 3:*\n"
                f"`/ban 123456789 motivo` (ID numérico)",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso correto:*\n\n"
            f"*Opção 1 (RECOMENDADO):*\n"
            f"Responda uma mensagem com `/ban motivo`\n\n"
            f"*Opção 2:*\n"
            f"`/ban @username motivo`\n\n"
            f"*Opção 3:*\n"
            f"`/ban 123456789 motivo` (ID numérico)",
            parse_mode='Markdown'
        )

async def send_ban_confirmation(update, user_id, user_name, username, reason):
    """Envia confirmação de banimento"""
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['ban']} Confirmar Ban", callback_data=f"ban_confirm_{user_id}_{reason}"),
            InlineKeyboardButton(f"{EMOJIS['error']} Cancelar", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚠️ *Confirmar Banimento*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📄 *Motivo:* {reason}\n\n"
        f"*Tem certeza que deseja banir este usuário permanentemente?*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /kick - expulsa o usuário mas permite que ele retorne"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    reason = "Sem motivo especificado"
    
    # Verifica se é reply
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
        if context.args:
            reason = " ".join(context.args)
        
        await send_kick_confirmation(update, user_id, user_name, username, reason)
        return
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
                if len(context.args) > 1:
                    reason = " ".join(context.args[1:])
                
                await send_kick_confirmation(update, user_id, user_name, username, reason)
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário {username_arg} não encontrado!\n\n"
                    f"✅ *SOLUÇÃO:* Responda uma mensagem do usuário com `/kick motivo`\n"
                    f"Ou peça para ele enviar uma mensagem primeiro.",
                    parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/kick @username motivo` ou responda com `/kick motivo`",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/kick @username motivo` ou responda com `/kick motivo`",
            parse_mode='Markdown'
        )

async def send_kick_confirmation(update, user_id, user_name, username, reason):
    """Envia confirmação de kick"""
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['kick']} Confirmar Kick", callback_data=f"kick_confirm_{user_id}_{reason}"),
            InlineKeyboardButton(f"{EMOJIS['error']} Cancelar", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"⚠️ *Confirmar Expulsão*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📄 *Motivo:* {reason}\n\n"
        f"*O usuário será expulso mas poderá retornar ao grupo.*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /mute com tempo e motivo - CORRIGIDO"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    duration = 60
    reason = "Sem motivo especificado"
    
    # Verifica se é reply
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
        if context.args:
            if context.args[0].isdigit():
                duration = int(context.args[0]) * 60
                if len(context.args) > 1:
                    reason = " ".join(context.args[1:])
            else:
                reason = " ".join(context.args)
        
        await send_mute_confirmation(update, user_id, user_name, username, duration, reason)
        return
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
                if len(context.args) > 1:
                    if context.args[1].isdigit():
                        duration = int(context.args[1]) * 60
                        if len(context.args) > 2:
                            reason = " ".join(context.args[2:])
                    else:
                        reason = " ".join(context.args[1:])
                
                await send_mute_confirmation(update, user_id, user_name, username, duration, reason)
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário não encontrado!\n✅ Use REPLY para 100% de confiabilidade.",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/mute @user 10 motivo` ou responda com `/mute 10 motivo`",
                parse_mode='Markdown'
            )
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/mute @user 10 motivo` ou responda com `/mute 10 motivo`",
            parse_mode='Markdown'
        )

async def send_mute_confirmation(update, user_id, user_name, username, duration, reason):
    """Envia confirmação de mute"""
    keyboard = [
        [
            InlineKeyboardButton(f"⏱️ 5min", callback_data=f"mute_confirm_{user_id}_300_{reason}"),
            InlineKeyboardButton(f"⏱️ 10min", callback_data=f"mute_confirm_{user_id}_600_{reason}"),
            InlineKeyboardButton(f"⏱️ 30min", callback_data=f"mute_confirm_{user_id}_1800_{reason}")
        ],
        [
            InlineKeyboardButton(f"⏱️ 1h", callback_data=f"mute_confirm_{user_id}_3600_{reason}"),
            InlineKeyboardButton(f"⏱️ 1d", callback_data=f"mute_confirm_{user_id}_86400_{reason}"),
            InlineKeyboardButton(f"🔇 Permanente", callback_data=f"mute_confirm_{user_id}_0_{reason}")
        ],
        [
            InlineKeyboardButton(f"⏱️ {duration//60}min", callback_data=f"mute_confirm_{user_id}_{duration}_{reason}"),
            InlineKeyboardButton(f"{EMOJIS['error']} Cancelar", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    duration_text = f"{duration//60} minutos" if duration > 0 else "permanentemente"
    
    await update.message.reply_text(
        f"🔇 *Confirmar Silenciamento*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"⏰ *Duração:* {duration_text}\n"
        f"📄 *Motivo:* {reason}\n\n"
        f"*Escolha a duração ou confirme:*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /warn com motivo"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    reason = "Sem motivo especificado"
    
    # Verifica se é reply
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
        if context.args:
            reason = " ".join(context.args)
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
                if len(context.args) > 1:
                    reason = " ".join(context.args[1:])
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário não encontrado!\n✅ Use REPLY para 100% de confiabilidade.",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/warn @user motivo` ou responda com `/warn motivo`",
                parse_mode='Markdown'
            )
            return
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/warn @user motivo` ou responda com `/warn motivo`",
            parse_mode='Markdown'
        )
        return
    
    # Adiciona advertência
    user_warnings[user_id] += 1
    warnings_count = user_warnings[user_id]
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['unwarn']} Remover Adv", callback_data=f"unwarn_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['ban']} Banir", callback_data=f"ban_confirm_{user_id}_{reason}")
        ],
        [InlineKeyboardButton(f"{EMOJIS['stats']} Ver Advertências", callback_data=f"warnings_{user_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{EMOJIS['warn']} *Usuário Advertido!*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"📄 *Motivo:* {reason}\n"
        f"📊 *Advertências:* {warnings_count}/3\n\n"
        f"{'🚫 *ATENÇÃO: Próxima advertência = BANIMENTO!*' if warnings_count >= 2 else '⚠️ Continue monitorando o usuário'}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    # atingiu 3 advertências, bane automaticamente
    if warnings_count >= MAX_WARNINGS:
        await ban_user_auto(update, context, user_id, f"3 advertências - Último: {reason}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unban com reply ou @username"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        user_id = target_user.id
        username = f"@{target_user.username}" if target_user.username else target_user.first_name
        user_name = target_user.first_name
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                username = username_arg
                user_name = target_user.first_name
            else:
                clean_username = username_arg[1:].lower() if username_arg.startswith('@') else username_arg
                if clean_username in username_to_id:
                    user_id = username_to_id[clean_username]
                    username = username_arg
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/unban @username` ou responda com `/unban`",
                parse_mode='Markdown'
            )
            return
    
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/unban @username` ou responda com `/unban`",
            parse_mode='Markdown'
        )
        return
    
    if not user_id:
        await update.message.reply_text(
            f"{EMOJIS['error']} Usuário não encontrado!",
            parse_mode='Markdown'
        )
        return
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['unban']} Confirmar Desban", callback_data=f"unban_confirm_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['error']} Cancelar", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔓 *Confirmar Desbanimento*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"🆔 *ID:* `{user_id}`\n\n"
        f"*Desbanir este usuário?*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unmute com reply ou @username"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário não encontrado!",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/unmute @username` ou responda com `/unmute`",
                parse_mode='Markdown'
            )
            return
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/unmute @username` ou responda com `/unmute`",
            parse_mode='Markdown'
        )
        return
    
    if user_id not in muted_users:
        await update.message.reply_text(
            f"{EMOJIS['info']} O usuário {username} não está silenciado!",
            parse_mode='Markdown'
        )
        return
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['unmute']} Confirmar Dessilenciar", callback_data=f"unmute_confirm_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['error']} Cancelar", callback_data="cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🔊 *Confirmar Dessilenciamento*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📝 *Username:* {username}\n\n"
        f"*Tem certeza que deseja dessilenciar este usuário?*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unwarn com reply ou @username"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário não encontrado!",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/unwarn @username` ou responda com `/unwarn`",
                parse_mode='Markdown'
            )
            return
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/unwarn @username` ou responda com `/unwarn`",
            parse_mode='Markdown'
        )
        return
    
    if user_warnings[user_id] > 0:
        user_warnings[user_id] -= 1
    
    warnings_count = user_warnings[user_id]
    
    await update.message.reply_text(
        f"{EMOJIS['success']} *Advertência Removida!*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"📊 *Advertências Atuais:* {warnings_count}/3",
        parse_mode='Markdown'
    )

async def check_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /warnings com reply ou @username"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
    
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário não encontrado!",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Uso:* `/warnings @username` ou responda com `/warnings`",
                parse_mode='Markdown'
            )
            return
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/warnings @username` ou responda com `/warnings`",
            parse_mode='Markdown'
        )
        return
    
    warnings_count = user_warnings[user_id]
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['warn']} Advertir", callback_data=f"warn_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['unwarn']} Remover Adv", callback_data=f"unwarn_{user_id}")
        ],
        [InlineKeyboardButton(f"{EMOJIS['ban']} Banir Usuário", callback_data=f"ban_confirm_{user_id}_Verificação")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "🟢" if warnings_count == 0 else "🟡" if warnings_count == 1 else "🟠" if warnings_count == 2 else "🔴"
    
    await update.message.reply_text(
        f"{EMOJIS['stats']} *Status de Advertências*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"📝 *Username:* {username}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📊 *Advertências:* {status_emoji} {warnings_count}/3\n\n"
        f"{'✅ Usuário limpo' if warnings_count == 0 else '⚠️ Monitorar usuário' if warnings_count == 1 else '🚫 Última advertência antes do ban!' if warnings_count == 2 else '❌ USUÁRIO DEVE SER BANIDO!'}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )


async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /info - mostra informações detalhadas do usuário"""
    await update_user_database(update.effective_user)
    
    user_id = None
    target_user = None
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
    else:
        target_user = update.effective_user
        user_id = target_user.id
    
    if not user_id or not target_user:
        await update.message.reply_text(
            f"{EMOJIS['error']} Usuário não encontrado!\n"
            f"✅ Use REPLY ou `/info @username` ou `/info ID`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status = member.status
        
        status_emoji = {
            'creator': '👑',
            'administrator': '👮',
            'member': '👤',
            'restricted': '🔇',
            'left': '🚪',
            'kicked': '🚫'
        }.get(status, '❓')
        
        status_text = {
            'creator': 'Criador',
            'administrator': 'Administrador',
            'member': 'Membro',
            'restricted': 'Restrito',
            'left': 'Saiu',
            'kicked': 'Banido'
        }.get(status, 'Desconhecido')
        
        warnings_count = user_warnings[user_id]
        is_muted = user_id in muted_users
        is_banned = user_id in blacklist
        
        db_info = ""
        if user_id in user_database:
            user_data = user_database[user_id]
            last_seen = user_data.get('last_seen', 0)
            if last_seen:
                last_seen_text = datetime.fromtimestamp(last_seen).strftime('%d/%m/%Y %H:%M')
                db_info = f"📅 *Última atividade:* {last_seen_text}\n"
        
        info_text = f"""
{EMOJIS['user']} *INFORMAÇÕES DO USUÁRIO*

👤 *Nome:* {target_user.first_name} {target_user.last_name or ''}
📝 *Username:* @{target_user.username or 'Sem username'}
🆔 *ID:* `{user_id}`
{status_emoji} *Status:* {status_text}

📊 *ESTATÍSTICAS:*
⚠️ *Advertências:* {warnings_count}/3
{'🔇 *Status:* Silenciado' if is_muted else ''}
{'🚫 *Status:* Banido' if is_banned else ''}

{db_info}
🤖 *Bot:* {'Sim' if target_user.is_bot else 'Não'}
        """
        
        await update.message.reply_text(info_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Erro ao buscar info do usuário: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao buscar informações do usuário.",
            parse_mode='Markdown'
        )

async def pin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /pin - fixa a mensagem respondida"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            f"{EMOJIS['error']} Responda a mensagem que deseja fixar com `/pin`",
            parse_mode='Markdown'
        )
        return
    
    try:
        await context.bot.pin_chat_message(
            update.effective_chat.id,
            update.message.reply_to_message.message_id,
            disable_notification=True
        )
        await update.message.reply_text(
            f"{EMOJIS['pin']} *Mensagem fixada com sucesso!*",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erro ao fixar mensagem: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao fixar mensagem. Verifique se o bot tem permissões.",
            parse_mode='Markdown'
        )

async def unpin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unpin - desfixa a mensagem respondida ou todas"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    try:
        if update.message.reply_to_message:
            await context.bot.unpin_chat_message(
                update.effective_chat.id,
                update.message.reply_to_message.message_id
            )
            await update.message.reply_text(
                f"{EMOJIS['success']} *Mensagem desfixada!*",
                parse_mode='Markdown'
            )
        else:
            await context.bot.unpin_all_chat_messages(update.effective_chat.id)
            await update.message.reply_text(
                f"{EMOJIS['success']} *Todas as mensagens foram desfixadas!*",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Erro ao desfixar: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao desfixar mensagem.",
            parse_mode='Markdown'
        )

async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /delete - deleta a mensagem respondida"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    if not update.message.reply_to_message:
        await update.message.reply_text(
            f"{EMOJIS['error']} Responda a mensagem que deseja deletar com `/delete`",
            parse_mode='Markdown'
        )
        return
    
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
    except Exception as e:
        logger.error(f"Erro ao deletar mensagem: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao deletar mensagem.",
            parse_mode='Markdown'
        )

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /id - mostra o ID do usuário"""
    await update_user_database(update.effective_user)
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    text = f"""
{EMOJIS['info']} *INFORMAÇÕES DE ID*

👤 *Seu ID:* `{user_id}`
💬 *ID do Chat:* `{chat_id}`
    """
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        text += f"\n👥 *ID do Usuário Mencionado:* `{target_user.id}`"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /admins - lista todos os administradores"""
    await update_user_database(update.effective_user)
    
    try:
        admins = await context.bot.get_chat_administrators(update.effective_chat.id)
        
        admin_list = f"{EMOJIS['admin']} *ADMINISTRADORES DO GRUPO*\n\n"
        
        for admin in admins:
            user = admin.user
            await update_user_database(user)
            
            emoji = "👑" if admin.status == "creator" else "👮"
            username = f"@{user.username}" if user.username else "Sem username"
            admin_list += f"{emoji} {user.first_name} - {username}\n"
        
        await update.message.reply_text(admin_list, parse_mode='Markdown')
        
    except BadRequest as e:
        logger.error(f"Erro ao listar admins (BadRequest): {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} *Erro ao listar administradores!*\n\n"
            f"Verifique se o bot é administrador do grupo.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Erro ao listar admins: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao listar administradores.\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def welcome_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /welcome on/off - ativa/desativa mensagens de boas-vindas"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    chat_id = update.effective_chat.id
    
    if not context.args:
        status = "ativadas" if group_settings[chat_id]['welcome_enabled'] else "desativadas"
        await update.message.reply_text(
            f"{EMOJIS['info']} Boas vindas estão *{status}*.\n"
            f"Use `/welcome on` ou `/welcome off`",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == 'on':
        group_settings[chat_id]['welcome_enabled'] = True
        await update.message.reply_text(
            f"{EMOJIS['success']} Mensagens de boas-vindas *ativadas*!",
            parse_mode='Markdown'
        )
    elif action == 'off':
        group_settings[chat_id]['welcome_enabled'] = False
        await update.message.reply_text(
            f"{EMOJIS['success']} Mensagens de boas-vindas *desativadas*!",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} Use `/welcome on` ou `/welcome off`",
            parse_mode='Markdown'
        )

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /setwelcome - define mensagem de boas-vindas"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    if not context.args:
        await update.message.reply_text(
            f"{EMOJIS['error']} Use `/setwelcome sua mensagem aqui`\n"
            f"Use {{name}} para mencionar o nome do usuário",
            parse_mode='Markdown'
        )
        return
    
    global welcome_message
    welcome_message = " ".join(context.args)
    
    await update.message.reply_text(
        f"{EMOJIS['success']} *Mensagem de boas-vindas definida!*\n\n"
        f"Prévia: {welcome_message.replace('{name}', 'Usuário')}",
        parse_mode='Markdown'
    )

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para novos membros - COM AUTO-DELETE"""
    chat_id = update.effective_chat.id
    
    if not group_settings[chat_id]['welcome_enabled']:
        return
    
    for new_member in update.message.new_chat_members:
        if new_member.is_bot:
            continue
        
        await update_user_database(new_member)
        
        if group_settings[chat_id]['locked']:
            try:
                await context.bot.ban_chat_member(chat_id, new_member.id)
                await update.message.reply_text(
                    f"{EMOJIS['lock']} Grupo bloqueado! Novo membro removido automaticamente."
                )
                continue
            except Exception as e:
                logger.error(f"Erro ao remover novo membro: {e}")
        
        welcome_text = welcome_message.replace('{name}', new_member.first_name)
        welcome_msg = await update.message.reply_text(f"{EMOJIS['welcome']} {welcome_text}")
        
        context.job_queue.run_once(
            delete_welcome_message,
            60,
            data={'chat_id': chat_id, 'message_id': welcome_msg.message_id}
        )

async def delete_welcome_message(context: ContextTypes.DEFAULT_TYPE):
    """Deleta mensagem de boas-vindas após 1 minuto"""
    job_data = context.job.data
    try:
        await context.bot.delete_message(
            chat_id=job_data['chat_id'],
            message_id=job_data['message_id']
        )
    except Exception as e:
        logger.debug(f"Não foi possível deletar mensagem de boas-vindas: {e}")

async def lock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /lock - bloqueia entrada de novos membros"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    chat_id = update.effective_chat.id
    group_settings[chat_id]['locked'] = True
    
    await update.message.reply_text(
        f"{EMOJIS['lock']} *Grupo bloqueado!*\n\n"
        f"Novos membros serão removidos automaticamente.",
        parse_mode='Markdown'
    )

async def unlock_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /unlock - desbloqueia entrada de novos membros"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    chat_id = update.effective_chat.id
    group_settings[chat_id]['locked'] = False
    
    await update.message.reply_text(
        f"{EMOJIS['unlock']} *Grupo desbloqueado!*\n\n"
        f"Novos membros podem entrar normally.",
        parse_mode='Markdown'
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler para botões inline"""
    query = update.callback_query
    
    if query is None:
        return
    
    await query.answer()
    
    data = query.data
    
    if data == "menu":
        await show_main_menu(query)
    elif data == "rules":
        await show_rules(query)
    elif data == "commands":
        await show_commands(query)
    elif data == "stats":
        await show_stats(query, context)
    elif data == "refresh_cache":
        await refresh_cache_action(query, context)
    elif data == "cancel":
        await query.edit_message_text(
            f"{EMOJIS['info']} *Ação cancelada!*",
            parse_mode='Markdown'
        )
    elif data.startswith("ban_confirm_"):
        parts = data.split("_", 2)
        user_id = int(parts[2].split("_")[0])
        reason = "_".join(parts[2].split("_")[1:]) if len(parts[2].split("_")) > 1 else "Sem motivo"
        await execute_ban(query, context, user_id, reason)
    elif data.startswith("kick_confirm_"):
        parts = data.split("_", 2)
        user_id = int(parts[2].split("_")[0])
        reason = "_".join(parts[2].split("_")[1:]) if len(parts[2].split("_")) > 1 else "Sem motivo"
        await execute_kick(query, context, user_id, reason)
    elif data.startswith("unban_confirm_"):
        user_id = int(data.split("_")[2])
        await execute_unban(query, context, user_id)
    elif data.startswith("mute_confirm_"):
        parts = data.split("_", 3)
        user_id = int(parts[2])
        duration = int(parts[3].split("_")[0])
        reason = "_".join(parts[3].split("_")[1:]) if len(parts[3].split("_")) > 1 else "Sem motivo"
        await execute_mute(query, context, user_id, duration, reason)
    elif data.startswith("unmute_confirm_"):
        user_id = int(data.split("_")[2])
        await execute_unmute(query, context, user_id)
    elif data.startswith("warn_"):
        user_id = int(data.split("_")[1])
        await execute_warn(query, context, user_id)
    elif data.startswith("unwarn_"):
        user_id = int(data.split("_")[1])
        await execute_unwarn(query, context, user_id)
    elif data.startswith("warnings_"):
        user_id = int(data.split("_")[1])
        await show_user_warnings(query, context, user_id)
    elif data.startswith("purge_"):
        if data == "purge_cancel":
            await query.edit_message_text(
                f"{EMOJIS['info']} Operação cancelada.",
                parse_mode='Markdown'
            )
        else:
            count = int(data.split("_")[1])
            
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            try:
                await query.edit_message_text(
                    f"{EMOJIS['clock']} Deletando {count} mensagens...",
                    parse_mode='Markdown'
                )
                
                deleted = 0
                failed = 0
                
                for i in range(count):
                    try:
                        await context.bot.delete_message(chat_id, message_id - i - 1)
                        deleted += 1
                        await asyncio.sleep(0.03)
                    except Exception as e:
                        failed += 1
                        logger.debug(f"Não foi possível deletar mensagem: {e}")
                
                try:
                    await query.message.delete()
                except:
                    pass
                
                # Envia confirmação
                confirmation = await context.bot.send_message(
                    chat_id,
                    f"{EMOJIS['success']} *{deleted} mensagens deletadas!*\n"
                    f"❌ Falhas: {failed}",
                    parse_mode='Markdown'
                )
                
                await asyncio.sleep(3)
                try:
                    await confirmation.delete()
                except:
                    pass
                    
            except Exception as e:
                logger.error(f"Erro ao purgar via botão: {e}")
                await query.edit_message_text(
                    f"{EMOJIS['error']} Erro ao deletar mensagens.\n\n`{str(e)}`",
                    parse_mode='Markdown'
                )

async def execute_ban(query, context, user_id, reason):
    """Executa o banimento do usuário"""
    try:
        await context.bot.ban_chat_member(query.message.chat_id, user_id)
        blacklist.add(user_id)
        
        user_data = user_database.get(user_id, {})
        user_name = user_data.get('first_name', 'Usuário')
        
        keyboard = [[InlineKeyboardButton(f"{EMOJIS['unban']} Desbanir", callback_data=f"unban_confirm_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"{EMOJIS['ban']} *Usuário Banido!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"📄 *Motivo:* {reason}\n"
            f"⏰ *Data:* {time.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"*Banimento realizado com sucesso!*",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        # Limpa dados
        if user_id in user_warnings:
            del user_warnings[user_id]
        if user_id in user_stickers:
            del user_stickers[user_id]
        if user_id in muted_users:
            del muted_users[user_id]
            
    except Exception as e:
        await query.edit_message_text(
            f"{EMOJIS['error']} *Erro ao banir!*\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def execute_kick(query, context, user_id, reason):
    """Executa a expulsão do usuário (pode retornar)"""
    try:
        await context.bot.ban_chat_member(query.message.chat_id, user_id)
        await context.bot.unban_chat_member(query.message.chat_id, user_id)
        
        user_data = user_database.get(user_id, {})
        user_name = user_data.get('first_name', 'Usuário')
        
        await query.edit_message_text(
            f"{EMOJIS['kick']} *Usuário Expulso!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"📄 *Motivo:* {reason}\n"
            f"⏰ *Data:* {time.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"*O usuário pode retornar ao grupo.*",
            parse_mode='Markdown'
        )
        
        if user_id in user_warnings:
            user_warnings[user_id] = 0
            
    except Exception as e:
        await query.edit_message_text(
            f"{EMOJIS['error']} *Erro ao expulsar!*\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def execute_unban(query, context, user_id):
    """Executa o desbanimento do usuário"""
    try:
        await context.bot.unban_chat_member(query.message.chat_id, user_id)
        if user_id in blacklist:
            blacklist.remove(user_id)
        user_warnings[user_id] = 0
        
        await query.edit_message_text(
            f"{EMOJIS['unban']} *Usuário Desbanido!*\n\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"⏰ *Data:* {time.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"*Desbanimento realizado! Advertências zeradas.*",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"{EMOJIS['error']} *Erro ao desbanir!*\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def execute_mute(query, context, user_id, duration, reason):
    """Executa o silenciamento do usuário"""
    try:
        permissions = ChatPermissions(
            can_send_messages=False,
            can_send_audios=False,
            can_send_documents=False,
            can_send_photos=False,
            can_send_videos=False,
            can_send_video_notes=False,
            can_send_voice_notes=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        until_date = None
        if duration > 0:
            until_date = time.time() + duration
            muted_users[user_id] = until_date
        else:
            muted_users[user_id] = 0
        
        await context.bot.restrict_chat_member(
            query.message.chat_id, 
            user_id, 
            permissions,
            until_date=until_date
        )
        
        user_data = user_database.get(user_id, {})
        user_name = user_data.get('first_name', 'Usuário')
        
        keyboard = [[InlineKeyboardButton(f"{EMOJIS['unmute']} Dessilenciar", callback_data=f"unmute_confirm_{user_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        duration_text = f"{duration//60} minutos" if duration > 0 else "permanentemente"
        
        await query.edit_message_text(
            f"{EMOJIS['mute']} *Usuário Silenciado!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"⏰ *Duração:* {duration_text}\n"
            f"📄 *Motivo:* {reason}\n"
            f"📅 *Data:* {time.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"*Usuário não pode mais enviar mensagens.*",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"{EMOJIS['error']} *Erro ao silenciar!*\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def execute_unmute(query, context, user_id):
    """Executa o dessilenciamento do usuário"""
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )
        await context.bot.restrict_chat_member(query.message.chat_id, user_id, permissions)
        if user_id in muted_users:
            del muted_users[user_id]
        
        user_data = user_database.get(user_id, {})
        user_name = user_data.get('first_name', 'Usuário')
        
        await query.edit_message_text(
            f"{EMOJIS['unmute']} *Usuário Dessilenciado!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"🆔 *ID:* `{user_id}`\n"
            f"⏰ *Data:* {time.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"*Usuário pode enviar mensagens novamente.*",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"{EMOJIS['error']} *Erro ao dessilenciar!*\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def execute_warn(query, context, user_id):
    """Executa advertência via botão"""
    user_warnings[user_id] += 1
    warnings_count = user_warnings[user_id]
    
    user_data = user_database.get(user_id, {})
    user_name = user_data.get('first_name', 'Usuário')
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['unwarn']} Remover", callback_data=f"unwarn_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['ban']} Banir", callback_data=f"ban_confirm_{user_id}_Advertência")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "🟢" if warnings_count == 0 else "🟡" if warnings_count == 1 else "🟠" if warnings_count == 2 else "🔴"
    
    await query.edit_message_text(
        f"{EMOJIS['warn']} *Usuário Advertido!*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📊 *Advertências:* {status_emoji} {warnings_count}/3\n\n"
        f"{'🚫 *Próxima = BAN!*' if warnings_count >= 2 else '⚠️ Monitorar'}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    
    if warnings_count >= MAX_WARNINGS:
        await execute_ban(query, context, user_id, "3 advertências")

async def execute_unwarn(query, context, user_id):
    """Remove advertência via botão"""
    if user_warnings[user_id] > 0:
        user_warnings[user_id] -= 1
    
    warnings_count = user_warnings[user_id]
    user_data = user_database.get(user_id, {})
    user_name = user_data.get('first_name', 'Usuário')
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['warn']} Advertir", callback_data=f"warn_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['ban']} Banir", callback_data=f"ban_confirm_{user_id}_Remoção")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "🟢" if warnings_count == 0 else "🟡" if warnings_count == 1 else "🟠" if warnings_count == 2 else "🔴"
    
    await query.edit_message_text(
        f"{EMOJIS['success']} *Advertência Removida!*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📊 *Advertências:* {status_emoji} {warnings_count}/3",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_user_warnings(query, context, user_id):
    """Mostra advertências do usuário via botão"""
    warnings_count = user_warnings[user_id]
    user_data = user_database.get(user_id, {})
    user_name = user_data.get('first_name', 'Usuário')
    
    keyboard = [
        [
            InlineKeyboardButton(f"{EMOJIS['warn']} Advertir", callback_data=f"warn_{user_id}"),
            InlineKeyboardButton(f"{EMOJIS['unwarn']} Remover", callback_data=f"unwarn_{user_id}")
        ],
        [InlineKeyboardButton(f"{EMOJIS['ban']} Banir", callback_data=f"ban_confirm_{user_id}_Verificação")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status_emoji = "🟢" if warnings_count == 0 else "🟡" if warnings_count == 1 else "🟠" if warnings_count == 2 else "🔴"
    
    await query.edit_message_text(
        f"{EMOJIS['stats']} *Status de Advertências*\n\n"
        f"👤 *Usuário:* {user_name}\n"
        f"🆔 *ID:* `{user_id}`\n"
        f"📊 *Advertências:* {status_emoji} {warnings_count}/3\n\n"
        f"{'✅ Limpo' if warnings_count == 0 else '⚠️ Monitorar' if warnings_count == 1 else '🚫 Última!' if warnings_count == 2 else '❌ BANIR!'}",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_main_menu(query):
    """Mostra menu principal"""
    keyboard = [
        [InlineKeyboardButton(f"{EMOJIS['rules']} Regras", callback_data="rules")],
        [InlineKeyboardButton(f"{EMOJIS['info']} Comandos", callback_data="commands")],
        [InlineKeyboardButton(f"{EMOJIS['stats']} Estatísticas", callback_data="stats")],
        [InlineKeyboardButton(f"{EMOJIS['refresh']} Atualizar", callback_data="refresh_cache")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{EMOJIS['bot']} *Menu Principal*\n\nEscolha uma opção:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_rules(query):
    """Mostra regras via botão"""
    rules_text = f"""
{EMOJIS['rules']} *REGRAS DO GRUPO*

{EMOJIS['ban']} *PROIBIÇÕES:*
• ❌ Links não autorizados
• ❌ Mensagens encaminhadas
• ❌ Spam de menções
• ❌ Conteúdo inadequado
• ❌ Flood de mensagens

{EMOJIS['warn']} *LIMITES:*
• ⚠️ Máx 5 figurinhas/10s
• ⚠️ 3 advertências = ban

{EMOJIS['admin']} *Admins têm imunidade*
    """
    
    keyboard = [[InlineKeyboardButton(f"{EMOJIS['bot']} Voltar", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        rules_text, 
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_commands(query):
    """Mostra comandos via botão"""
    commands_text = f"""
{EMOJIS['bot']} *COMANDOS PRINCIPAIS*

🔨 *Moderação:*
`/ban` `/kick` `/mute` `/warn`
`/unban` `/unmute` `/unwarn`

📌 *Mensagens:*
`/pin` `/unpin` `/delete`

👤 *Info:*
`/info` `/id` `/warnings` `/admins`

⚙️ *Config:*
`/welcome` `/lock` `/unlock`

Use `/help` para lista completa!
    """
    
    keyboard = [[InlineKeyboardButton(f"{EMOJIS['bot']} Voltar", callback_data="menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        commands_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /stats - mostra estatísticas do grupo"""
    await update_user_database(update.effective_user)
    
    try:
        chat_id = update.effective_chat.id
        
        # Conta membros do grupo
        try:
            member_count = await context.bot.get_chat_member_count(chat_id)
        except:
            member_count = "N/A"
        
        # Conta admins
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_count = len(admins)
        except:
            admin_count = "N/A"
        
        total_warnings = sum(user_warnings.values())
        banned_users = len(blacklist)
        muted_count = len(muted_users)
        total_users = len(user_database)
        users_with_warnings = len(user_warnings)
        
        stats_text = f"""
{EMOJIS['stats']} *ESTATÍSTICAS DO GRUPO*

👥 *Membros:*
• Total no grupo: {member_count}
• No banco de dados: {total_users}
• Administradores: {admin_count}

{EMOJIS['warn']} *Moderação:*
• Usuários com advertências: {users_with_warnings}
• Total de advertências: {total_warnings}
• Usuários banidos: {banned_users}
• Usuários silenciados: {muted_count}

🤖 *Bot:*
• Status: Online
• Cache de admins: {len(admin_cache)} entradas

{EMOJIS['clock']} *Atualizado:* {time.strftime('%d/%m/%Y às %H:%M:%S')}
        """
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Erro ao mostrar stats: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao carregar estatísticas.\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def show_stats(query, context):
    """Mostra estatísticas do grupo"""
    try:
        chat_id = query.message.chat_id
        
        try:
            member_count = await context.bot.get_chat_member_count(chat_id)
        except:
            member_count = "N/A"
        
        # Conta admins
        try:
            admins = await context.bot.get_chat_administrators(chat_id)
            admin_count = len(admins)
        except:
            admin_count = "N/A"
        
        total_warnings = sum(user_warnings.values())
        banned_users = len(blacklist)
        muted_count = len(muted_users)
        total_users = len(user_database)
        users_with_warnings = len(user_warnings)
        
        uptime = "Online"
        
        stats_text = f"""
{EMOJIS['stats']} *ESTATÍSTICAS DO GRUPO*

👥 *Membros:*
• Total no grupo: {member_count}
• No banco de dados: {total_users}
• Administradores: {admin_count}

{EMOJIS['warn']} *Moderação:*
• Usuários com advertências: {users_with_warnings}
• Total de advertências: {total_warnings}
• Usuários banidos: {banned_users}
• Usuários silenciados: {muted_count}

🤖 *Bot:*
• Status: {uptime}
• Cache de admins: {len(admin_cache)} entradas

{EMOJIS['clock']} *Atualizado:* {time.strftime('%d/%m/%Y às %H:%M:%S')}
        """
        
        keyboard = [[InlineKeyboardButton(f"{EMOJIS['bot']} Voltar", callback_data="menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            stats_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Erro ao mostrar stats: {e}")
        await query.edit_message_text(
            f"{EMOJIS['error']} Erro ao carregar estatísticas.\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def refresh_cache_action(query, context):
    """Atualiza o cache via botão"""
    admin_cache.clear()
    total_users = len(user_database)
    
    await query.edit_message_text(
        f"{EMOJIS['refresh']} *Cache atualizado!*\n\n"
        f"📊 Usuários salvos: {total_users}",
        parse_mode='Markdown'
    )

async def handle_stickers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitora figurinhas e aplica limites"""
    if not update.message or not update.message.from_user:
        return
    
    # Atualiza banco de dados
    await update_user_database(update.message.from_user)
    
    user_id = update.message.from_user.id
    
    if await check_admin(update, context):
        return
    
    current_time = time.time()
    user_stickers[user_id].append(current_time)
    
    if len(user_stickers[user_id]) >= MAX_STICKERS:
        first_sticker_time = user_stickers[user_id][0]
        if current_time - first_sticker_time <= TIME_WINDOW:
            await handle_rule_violation(update, context, user_id, "Excesso de figurinhas (5 em 10s)")

async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitora todas as mensagens para detectar violações"""
    if not update.message or not update.message.from_user:
        return
    
    await update_user_database(update.message.from_user)
    
    user_id = update.message.from_user.id
    
    if await check_admin(update, context):
        return
    
    if update.message.forward_from or update.message.forward_from_chat:
        await handle_rule_violation(update, context, user_id, "Mensagem encaminhada")
        return
    
    text_to_check = ""
    if update.message.text:
        text_to_check = update.message.text
    elif update.message.caption:
        text_to_check = update.message.caption
    
    if text_to_check:
        if URL_REGEX.search(text_to_check):
            await handle_rule_violation(update, context, user_id, "Envio de links")
            return
        
        if await detect_spam_mentions(text_to_check, update.effective_chat.id, context):
            await handle_rule_violation(update, context, user_id, "Spam de menções")
            return
    
    if update.message.text:
        current_time = time.time()
        user_messages[user_id].append(current_time)
        
        if len(user_messages[user_id]) >= MAX_MESSAGES:
            first_msg_time = user_messages[user_id][0]
            if current_time - first_msg_time <= MESSAGE_TIME_WINDOW:
                await handle_rule_violation(update, context, user_id, "Flood de mensagens")

async def detect_spam_mentions(text: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Detecta se há menções spam"""
    if not text:
        return False
    
    at_count = text.count('@')
    
    if at_count > 3:
        return True
    
    mentions = re.findall(r'@(\w+)', text)
    if mentions and at_count > 2:
        return True
    
    return False

async def handle_rule_violation(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str):
    """Lida com violações de regras"""
    chat_id = update.effective_chat.id
    
    try:
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Não foi possível deletar mensagem: {e}")
        
        if user_id not in muted_users:
            try:
                permissions = ChatPermissions(
                    can_send_messages=False,
                    can_send_audios=False,
                    can_send_documents=False,
                    can_send_photos=False,
                    can_send_videos=False,
                    can_send_video_notes=False,
                    can_send_voice_notes=False,
                    can_send_polls=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                )
                await context.bot.restrict_chat_member(chat_id, user_id, permissions)
                muted_users[user_id] = time.time() + 3600
            except Exception as e:
                logger.error(f"Falha ao silenciar: {e}")
        
        user_warnings[user_id] += 1
        warnings_count = user_warnings[user_id]
        
        user_data = user_database.get(user_id, {})
        user_name = user_data.get('first_name', 'Usuário')
        
        await context.bot.send_message(
            chat_id,
            f"{EMOJIS['warn']} *Violação de Regras!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"📝 *Motivo:* {reason}\n"
            f"🔇 *Ação:* Silenciado por 1 hora\n"
            f"📊 *Advertências:* {warnings_count}/3\n\n"
            f"ℹ️ Use /rules para ver as regras",
            parse_mode='Markdown'
        )
        
        if warnings_count >= MAX_WARNINGS:
            await ban_user_auto(update, context, user_id, f"{reason} + {MAX_WARNINGS} advertências")
    
    except Exception as e:
        logger.error(f"Erro ao lidar com violação: {e}")

async def ban_user_auto(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str):
    """Banir usuário automaticamente"""
    chat_id = update.effective_chat.id
    try:
        await context.bot.ban_chat_member(chat_id, user_id)
        blacklist.add(user_id)
        
        user_data = user_database.get(user_id, {})
        user_name = user_data.get('first_name', 'Usuário')
        
        await context.bot.send_message(
            chat_id,
            f"{EMOJIS['ban']} *Banimento Automático!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"📝 *Motivo:* {reason}\n"
            f"❌ Limite de advertências atingido",
            parse_mode='Markdown'
        )
        
        if user_id in user_warnings:
            del user_warnings[user_id]
        if user_id in user_stickers:
            del user_stickers[user_id]
        if user_id in muted_users:
            del muted_users[user_id]
    except Exception as e:
        logger.error(f"Erro ao banir: {e}")

async def check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Verifica se o usuário é administrador - COM CACHE"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    cache_key = f"{chat_id}_{user_id}"
    
    if cache_key in admin_cache:
        cached_data = admin_cache[cache_key]
        if time.time() - cached_data['timestamp'] < 120:
            return cached_data['is_admin']
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in ['administrator', 'creator']
        
        admin_cache[cache_key] = {
            'is_admin': is_admin,
            'timestamp': time.time()
        }
        
        return is_admin
    except Exception as e:
        logger.error(f"Erro ao verificar admin: {e}")
        return False

async def purge_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /purge - deleta múltiplas mensagens com botões interativos"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    if update.message.reply_to_message or (context.args and len(context.args) > 0):
        await execute_purge(update, context)
    else:
        keyboard = [
            [
                InlineKeyboardButton("🗑️ Últimas 10", callback_data="purge_10"),
                InlineKeyboardButton("🗑️ Últimas 50", callback_data="purge_50")
            ],
            [
                InlineKeyboardButton("🗑️ Últimas 100", callback_data="purge_100"),
                InlineKeyboardButton("❌ Cancelar", callback_data="purge_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"{EMOJIS['info']} *PURGE - Deletar Mensagens*\n\n"
            f"Escolha quantas mensagens deletar:\n\n"
            f"💡 *Outras opções:*\n"
            f"• `/purge 25` - Deleta últimas 25 mensagens\n"
            f"• Responda uma mensagem e use `/purge` - Deleta da mensagem respondida até a atual",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def execute_purge(update: Update, context: ContextTypes.DEFAULT_TYPE, count: int = None):
    """Executa o purge de mensagens"""
    try:
        if update.message.reply_to_message:
            start_id = update.message.reply_to_message.message_id
            end_id = update.message.message_id
            chat_id = update.effective_chat.id
            
            deleted = 0
            failed = 0
            
            for msg_id in range(start_id, end_id + 1):
                try:
                    await context.bot.delete_message(chat_id, msg_id)
                    deleted += 1
                    await asyncio.sleep(0.03)
                except Exception as e:
                    failed += 1
                    logger.debug(f"Não foi possível deletar mensagem {msg_id}: {e}")
            
            confirmation = await update.message.reply_text(
                f"{EMOJIS['success']} *Purge Completo!*\n\n"
                f"✅ Deletadas: {deleted}\n"
                f"❌ Falhas: {failed}",
                parse_mode='Markdown'
            )
            
            await asyncio.sleep(3)
            try:
                await confirmation.delete()
            except:
                pass
                
        elif count or (context.args and context.args[0].isdigit()):
            if not count:
                count = int(context.args[0])
            
            if count > 100:
                await update.message.reply_text(
                    f"{EMOJIS['error']} *Limite excedido!*\n\nMáximo: 100 mensagens por vez.",
                    parse_mode='Markdown'
                )
                return
            
            message_id = update.message.message_id
            chat_id = update.effective_chat.id
            
            deleted = 0
            failed = 0
            
            for i in range(count + 1):
                try:
                    await context.bot.delete_message(chat_id, message_id - i)
                    deleted += 1
                    await asyncio.sleep(0.03)
                except Exception as e:
                    failed += 1
                    logger.debug(f"Não foi possível deletar mensagem {message_id - i}: {e}")
            
            confirmation = await context.bot.send_message(
                chat_id,
                f"{EMOJIS['success']} *{deleted} mensagens deletadas!*\n"
                f"❌ Falhas: {failed}",
                parse_mode='Markdown'
            )
            
            await asyncio.sleep(3)
            try:
                await confirmation.delete()
            except:
                pass
                
    except Exception as e:
        logger.error(f"Erro ao purgar mensagens: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro ao deletar mensagens.\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def promote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /promote - promove usuário a administrador"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} Usuário não encontrado!\n✅ Use REPLY para 100% de confiabilidade.",
                    parse_mode='Markdown'
                )
                return
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/promote @username` ou responda com `/promote`",
            parse_mode='Markdown'
        )
        return
    
    try:
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            user_id,
            can_manage_chat=True,
            can_delete_messages=True,
            can_manage_video_chats=False,
            can_restrict_members=True,
            can_promote_members=False,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_topics=False
        )
        
        await update.message.reply_text(
            f"{EMOJIS['promote']} *Usuário Promovido!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"📝 *Username:* {username}\n"
            f"🆔 *ID:* `{user_id}`\n\n"
            f"✅ *Agora é administrador do grupo!*",
            parse_mode='Markdown'
        )
        
        admin_cache.clear()
        
    except Exception as e:
        logger.error(f"Erro ao promover: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} *Erro ao promover usuário!*\n\n"
            f"Verifique se você tem permissão para promover membros.",
            parse_mode='Markdown'
        )

async def demote_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /demote - remove privilégios de administrador"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    user_id = None
    user_name = "Usuário"
    username = ""
    
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        await update_user_database(target_user)
        user_id = target_user.id
        user_name = target_user.first_name
        username = f"@{target_user.username}" if target_user.username else user_name
    elif context.args and len(context.args) >= 1:
        username_arg = context.args[0]
        if username_arg.startswith('@') or username_arg.isdigit():
            clean_arg = username_arg[1:] if username_arg.startswith('@') else username_arg
            target_user = await find_user_by_username(clean_arg, update, context)
            if target_user:
                user_id = target_user.id
                user_name = target_user.first_name
                username = username_arg
            else:
                await update.message.reply_text(
                    f"{EMOJIS['error']} *Usuário não encontrado!*\n\n"
                    f"💡 *Soluções:*\n"
                    f"1️⃣ Use REPLY (responda a mensagem do usuário)\n"
                    f"2️⃣ Use o ID numérico: `/demote 123456789`\n"
                    f"3️⃣ Peça para o usuário enviar uma mensagem primeiro",
                    parse_mode='Markdown'
                )
                return
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} *Uso:* `/demote @username` ou responda com `/demote`",
            parse_mode='Markdown'
        )
        return
    
    try:
        chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
        if chat_member.status not in ['administrator', 'creator']:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Erro!*\n\nEste usuário não é administrador.",
                parse_mode='Markdown'
            )
            return
        
        if chat_member.status == 'creator':
            await update.message.reply_text(
                f"{EMOJIS['error']} *Erro!*\n\nNão é possível rebaixar o criador do grupo!",
                parse_mode='Markdown'
            )
            return
        
        await context.bot.promote_chat_member(
            update.effective_chat.id,
            user_id,
            can_manage_chat=False,
            can_delete_messages=False,
            can_manage_video_chats=False,
            can_restrict_members=False,
            can_promote_members=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False,
            can_manage_topics=False,
            can_post_messages=False,
            can_edit_messages=False
        )
        
        await update.message.reply_text(
            f"{EMOJIS['demote']} *Privilégios Removidos!*\n\n"
            f"👤 *Usuário:* {user_name}\n"
            f"📝 *Username:* {username}\n"
            f"🆔 *ID:* `{user_id}`\n\n"
            f"✅ *Agora é membro comum do grupo!*",
            parse_mode='Markdown'
        )
        
        admin_cache.clear()
        
    except BadRequest as e:
        error_msg = str(e).lower()
        if "not enough rights" in error_msg:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Erro de Permissão!*\n\n"
                f"Verifique se você tem permissão para gerenciar administradores.",
                parse_mode='Markdown'
            )
        elif "user_not_participant" in error_msg:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Erro!*\n\nUsuário não está no grupo.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['error']} *Erro ao remover privilégios!*\n\n`{str(e)}`",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Erro ao rebaixar usuário: {e}")
        await update.message.reply_text(
            f"{EMOJIS['error']} Erro inesperado.\n\n`{str(e)}`",
            parse_mode='Markdown'
        )

async def antiraid_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /antiraid on/off - ativa/desativa proteção anti-raid"""
    if not await check_admin(update, context):
        return
    
    await update_user_database(update.effective_user)
    
    chat_id = update.effective_chat.id
    
    if not context.args:
        status = "ativado" if group_settings[chat_id]['antiraid'] else "desativado"
        await update.message.reply_text(
            f"{EMOJIS['info']} *Anti-Raid:* {status}\n\n"
            f"*O que é Anti-Raid?*\n"
            f"Proteção contra ataques de spam em massa. Quando ativado:\n"
            f"• Novos membros são monitorados rigorosamente\n"
            f"• Limites de mensagens mais rígidos\n"
            f"• Banimentos automáticos mais rápidos\n\n"
            f"Use `/antiraid on` ou `/antiraid off`",
            parse_mode='Markdown'
        )
        return
    
    action = context.args[0].lower()
    
    if action == 'on':
        group_settings[chat_id]['antiraid'] = True
        await update.message.reply_text(
            f"{EMOJIS['success']} *Anti-Raid ATIVADO!*\n\n"
            f"🛡️ *Proteções ativas:*\n"
            f"• Monitoramento intensivo de novos membros\n"
            f"• Limites de mensagens reduzidos\n"
            f"• Banimentos automáticos acelerados\n"
            f"• Detecção de padrões de spam\n\n"
            f"⚠️ *Recomendado durante ataques de spam!*",
            parse_mode='Markdown'
        )
    elif action == 'off':
        group_settings[chat_id]['antiraid'] = False
        await update.message.reply_text(
            f"{EMOJIS['success']} *Anti-Raid DESATIVADO!*\n\n"
            f"✅ Proteções voltaram ao normal.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"{EMOJIS['error']} Use `/antiraid on` ou `/antiraid off`",
            parse_mode='Markdown'
        )

def main():
    """Função principal"""
    application = Application.builder().token(TOKEN).build()
    
    # Handlers de comandos
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rules", rules))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("unmute", unmute_user))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler("unwarn", unwarn_user))
    application.add_handler(CommandHandler("warnings", check_warnings))
    application.add_handler(CommandHandler("refresh", refresh_cache_command))
    application.add_handler(CommandHandler("info", user_info))
    application.add_handler(CommandHandler("id", get_id))
    application.add_handler(CommandHandler("pin", pin_message))
    application.add_handler(CommandHandler("unpin", unpin_message))
    application.add_handler(CommandHandler("delete", delete_message))
    application.add_handler(CommandHandler("admins", list_admins))
    application.add_handler(CommandHandler("stats", stats_command))  # Added stats command
    application.add_handler(CommandHandler("welcome", welcome_toggle))
    application.add_handler(CommandHandler("setwelcome", set_welcome))
    application.add_handler(CommandHandler("lock", lock_group))
    application.add_handler(CommandHandler("unlock", unlock_group))
    application.add_handler(CommandHandler("purge", purge_messages))
    application.add_handler(CommandHandler("promote", promote_user))
    application.add_handler(CommandHandler("demote", demote_user))
    application.add_handler(CommandHandler("antiraid", antiraid_toggle))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
    
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_stickers))
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.PHOTO | filters.VIDEO | filters.Document.ALL, 
        handle_all_messages
    ))
    
    print("=" * 60)
    print("🎉 BOT DE GERENCIAMENTO COMPLETO INICIADO!")
    print("=" * 60)
    print("\n✨ FUNCIONALIDADES ATIVAS:")
    print("   ✅ Sistema de cache automático de usuários")
    print("   ✅ Comandos por REPLY (100% confiável)")
    print("   ✅ Comandos por @username (usa banco local)")
    print("   ✅ Ban, Kick, Mute, Warn completos")
    print("   ✅ Pin/Unpin de mensagens")
    print("   ✅ Purge com botões interativos")
    print("   ✅ Promote/Demote administradores")
    print("   ✅ Estatísticas do grupo (/stats)")
    print("   ✅ Informações de usuários (/info)")
    print("   ✅ Mensagens de boas-vindas (auto-delete 1min)")
    print("   ✅ Proteção anti-raid avançada")
    print("   ✅ Lista de administradores")
    print("   ✅ Moderação automática")
    print("   ✅ Interface com botões interativos")
    print("\n💡 DICA: Use REPLY sempre que possível!")
    print("=" * 60)
    
    application.run_polling()

if __name__ == '__main__':
    main()
