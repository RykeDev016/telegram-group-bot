# 🤖 Telegram Group Management Bot

Um bot **completo e avançado de moderação para grupos do Telegram**, desenvolvido em **Python** com a biblioteca [`python-telegram-bot`](https://python-telegram-bot.org).  
Oferece um **sistema poderoso de moderação, proteção anti-raid, banco de dados local, estatísticas detalhadas e interface interativa com botões**.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Ativo-success.svg)

---

## ✨ Funcionalidades Principais

### 🛡️ Sistema de Moderação
- Banimento **inteligente com confirmação via botões**
- **Advertências automáticas** (3 advertências = ban automático)
- **Silenciamento temporário** com durações personalizadas
- Expulsão (**kick**) com possibilidade de retorno
- **Remoção de mensagens**, fixar/desfixar e purge
- **Sistema anti-flood** e anti-spam

### 🔍 Gerenciamento de Usuários
- Banco de dados **local e persistente**
- Busca por **@username, ID ou reply**
- **Cache inteligente** de administradores
- Mapeamento `username → ID`

### ⚡ Funcionalidades Extras
- **Anti-Raid** (bloqueio de ataques em massa)
- **Mensagens de boas-vindas** com auto-delete (1 min)
- **Estatísticas do grupo e do banco**
- **Interface com botões inline** para todas as ações
- **Promoção e remoção de administradores**

### 🤖 Automação
- Detecção de **flood de mensagens** (8 em 5 segundos)
- Limite de **figurinhas** (5 em 10 segundos)
- Bloqueio de **links não autorizados**
- Bloqueio de **mensagens encaminhadas**
- **Prevenção de spam de menções**

---

## 🏗️ Estrutura do Projeto

telegram-group-bot/
│
├── bot.py              # Código principal do bot
├── README.md           # Documentação do projeto
├── requirements.txt    # Dependências Python
└── data/               # Banco de dados local (gerado automaticamente)

---

## 🚀 Instalação e Configuração

### ✅ Pré-requisitos
- **Python 3.8+**
- Uma conta no Telegram
- **Token de Bot** obtido via [@BotFather](https://t.me/BotFather)

### 📦 Instalação

1. **Clone o repositório**
   git clone https://github.com/rykRykeDev016edev/telegram-group-bot.git  
   cd telegram-group-bot

2. **Crie um ambiente virtual**
   python -m venv venv  
   source venv/bin/activate  # Linux/macOS  
   venv\Scripts\activate     # Windows

3. **Instale as dependências**
   pip install -r requirements.txt

4. **Configure seu token**
   Edite o arquivo `bot.py` e substitua:  
   TOKEN = "TOKEN BURRO"  
   pelo seu token real fornecido pelo @BotFather.

5. **Execute o bot**
   python bot.py

---

## 💡 Como Usar

Adicione o bot como **administrador do seu grupo** com permissões de:  
- Apagar mensagens  
- Banir/mutar usuários  
- Fixar mensagens  

Em seguida, use os comandos abaixo 👇

### 🔨 Moderação
/ban @user motivo       → Banir usuário  
/kick @user motivo      → Expulsar (pode voltar)  
/mute @user 10 motivo   → Silenciar (minutos)  
/warn @user motivo      → Advertir (3 = ban)  
/unban @user            → Desbanir  
/unmute @user           → Dessilenciar  
/unwarn @user           → Remover advertência  
/warnings @user         → Ver advertências  

### ⚙️ Administração
/welcome on/off         → Ativar/Desativar boas-vindas  
/setwelcome texto       → Definir mensagem de boas-vindas  
/lock ou /unlock        → Bloquear/desbloquear grupo  
/antiraid on/off        → Proteção anti-raid  
/promote @user          → Promover a admin  
/demote @user           → Remover admin  
/refresh                → Atualizar cache  

### 👤 Informações
/info @user             → Informações completas do usuário  
/id                     → Ver IDs (seu, do grupo e reply)  
/stats                  → Estatísticas gerais  
/admins                 → Lista de administradores  

### 🧹 Mensagens
/pin                    → Fixar mensagem (via reply)  
/unpin                  → Desfixar  
/delete                 → Deletar mensagem (via reply)  
/purge 10               → Apagar últimas 10 mensagens  

---

## 📊 Exemplo de Interface

O bot envia mensagens interativas com botões inline para confirmação de ações:

⚠️ **Confirmar Banimento**  
👤 *Usuário:* João  
📄 *Motivo:* Spam  
[🚫 Confirmar Ban] [❌ Cancelar]

---

## 🧠 Tecnologias Utilizadas

- **Python 3.10**
- **python-telegram-bot v20+**
- **asyncio**
- **logging**
- **Regex (detecção de links)**
- **Banco de dados local (dicionários persistentes)**

---

## 📈 Futuras Melhorias

- Integração com banco de dados **SQLite**
- Sistema de **logs persistentes**
- **Painel web de administração**
- **Suporte multilíngue (i18n)**
- **Backup automático de usuários**

---

## 🧑‍💻 Contribuições

Contribuições são bem-vindas!

1. Faça um **fork** do repositório  
2. Crie uma **branch** com sua feature:  
   git checkout -b feature/nova-feature  
3. Faça o **commit** das mudanças:  
   git commit -m 'Adiciona nova funcionalidade'  
4. **Envie para o repositório remoto:**  
   git push origin feature/nova-feature  
5. Crie um **Pull Request**

---

## ⚖️ Licença

Este projeto está sob a licença **MIT**.  
Você pode usar, modificar e distribuir livremente, desde que mantenha os créditos originais.

---

## 💬 Contato

📢 **Autor:** [@rykedev](https://github.com/RykeDev016)  
💬 **Telegram:** [@RykeDev](https://t.me/RykeDev)  
---

⭐ *Se este projeto te ajudou, deixe uma estrela no GitHub!*
