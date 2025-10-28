# 🤖 Telegram Group Management Bot

Um bot de moderação completo e avançado para grupos do Telegram, desenvolvido em Python com a biblioteca `python-telegram-bot`. Oferece sistema completo de moderação, proteção anti-raid, banimento inteligente e muito mais.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Características Principais

### 🛡️ Sistema de Moderação
- **Banimento inteligente** com confirmação por botões
- **Sistema de advertências** (3 advertências = ban automático)
- **Silenciamento temporário** com múltiplas durações
- **Expulsão de usuários** (kick) com possibilidade de retorno
- **Moderação automática** por violação de regras

### 🔍 Busca Avançada de Usuários
- **Banco de dados local** de usuários para busca rápida
- **Múltiplos métodos** de identificação (reply, @username, ID)
- **Cache inteligente** de administradores
- **Sistema de mapeamento** username → ID

### 🎯 Funcionalidades Especiais
- **Proteção Anti-Raid** contra ataques em massa
- **Mensagens de boas-vindas** com auto-delete (1 minuto)
- **Purge de mensagens** com interface interativa
- **Promoção/remoção** de administradores
- **Estatísticas completas** do grupo
- **Interface com botões** inline para todas as ações

### ⚡ Moderação Automática
- Detecção de **flood de mensagens** (8 em 5 segundos)
- Limite de **figurinhas** (5 em 10 segundos)
- Bloqueio de **links não autorizados**
- Prevenção de **spam de menções**
- Bloqueio de **mensagens encaminhadas**

## 🚀 Instalação

### Pré-requisitos
- Python 3.8 ou superior
- Token do Bot do Telegram (@BotFather)

### 1. Clone o repositório
```bash
git clone https://github.com/rykedev/telegram-group-bot.git
cd telegram-group-bot
