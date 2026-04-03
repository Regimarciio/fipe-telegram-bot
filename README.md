
##FIPE TELEGRAM BOT - DOCUMENTACAO OFICIAL


SOBRE O PROJETO
================================================================================

Bot para consulta e monitoramento da tabela FIPE de motos via Telegram.
O sistema permite consultar valores oficiais, monitorar precos automaticamente
e receber alertas de alteracoes.

FUNCIONALIDADES
================================================================================

- Consulta de marcas, modelos e anos da tabela FIPE
- Paginacao automatica para listas extensas (20 itens por pagina)
- Monitoramento de veiculos com alertas de mudanca de preco
- Historico de valores monitorados
- Persistencia em PostgreSQL
- Containerizado com Docker Compose

TECNOLOGIAS UTILIZADAS
================================================================================

- Python 3.11
- python-telegram-bot 20.7
- PostgreSQL 15
- Docker e Docker Compose
- API FIPE (Parallelum)

PRE-REQUISITOS
================================================================================

- Docker e Docker Compose instalados
- Token de bot do Telegram (via @BotFather)
- Servidor com acesso a internet

INSTALACAO E CONFIGURACAO
================================================================================

1. Clone o repositorio

   git clone https://github.com/Regimarciio/fipe-telegram-bot.git
   cd fipe-telegram-bot

2. Configure o arquivo de ambiente

   Crie um arquivo .env na raiz do projeto com o conteudo abaixo:

   TELEGRAM_TOKEN=seu_token_aqui
   DB_HOST=db
   DB_NAME=fipe
   DB_USER=fipe
   DB_PASS=Fipe@2024Secure

3. Inicie os containers

   docker-compose up -d --build

4. Verifique os logs

   docker logs fipe_bot -f

ESTRUTURA DO PROJETO
================================================================================

   fipe-telegram-bot/
   ├── bot_completo.py      # Codigo principal do bot
   ├── scheduler_job.py     # Agendador de monitoramento
   ├── docker-compose.yml   # Configuracao dos containers
   ├── Dockerfile           # Build da imagem Python
   ├── requirements.txt     # Dependencias Python
   └── .env                 # Variaveis de ambiente (nao versionado)

COMANDOS DO BOT
================================================================================

   COMANDO     | DESCRICAO
   ------------|------------------------------------------------
   /start      | Inicia o bot e exibe o menu principal

MENU PRINCIPAL
================================================================================

   OPCAO                 | DESCRICAO
   ----------------------|---------------------------------------
   Consultar moto        | Busca veiculos na tabela FIPE
   Minhas motos          | Lista veiculos monitorados
   Historico             | Exibe alteracoes de preco
   Remover               | Cancela monitoramento

FLUXO DE CONSULTA
================================================================================

   1. Selecione a marca do veiculo
   2. Escolha o modelo (navegacao paginada)
   3. Selecione o ano de fabricacao
   4. Visualize o valor FIPE atual
   5. Opcao de adicionar ao monitoramento

MONITORAMENTO AUTOMATICO
================================================================================

O sistema verifica diariamente os precos dos veiculos monitorados e envia
alertas quando ha alteracao na tabela FIPE.

MANUTENCAO
================================================================================

   Reiniciar servicos
   docker-compose restart

   Visualizar logs
   docker logs fipe_bot -f --tail 50

   Parar servicos
   docker-compose down

   Backup do banco de dados
   docker exec fipe_db pg_dump -U fipe fipe > backup_$(date +%Y%m%d).sql

API UTILIZADA
================================================================================

O bot consome a API publica do Parallelum:

   https://parallelum.com.br/fipe/api/v1/motos

LICENCA
================================================================================

Este projeto e de uso livre para fins educacionais e pessoais.

CONTATO
================================================================================

   Reginaldo Marcilio
   reginaldo.marcilio@gmail.com

   Link do Projeto:
   https://github.com/Regimarciio/fipe-telegram-bot

================================================================================
