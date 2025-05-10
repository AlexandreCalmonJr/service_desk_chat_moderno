# Assistente de Service Desk 🤖

Bem-vindo ao **Assistente de Service Desk**, uma aplicação web desenvolvida para fornecer suporte técnico rápido e eficiente através de FAQs (perguntas frequentes) interativas. Com um chat integrado que utiliza **Processamento de Linguagem Natural (NLP)** via Dialogflow, o sistema entende perguntas dos usuários e retorna respostas úteis, além de permitir a gestão de FAQs por administradores.

## 📋 Visão Geral

O Assistente de Service Desk é ideal para equipes de TI que desejam oferecer suporte interno ou externo de forma automatizada. Ele combina uma interface amigável, gestão de FAQs, e um chat inteligente para responder a perguntas comuns sobre hardware, software, rede, e mais.

### Funcionalidades Principais
- **Chat com NLP**: Utiliza o Dialogflow para interpretar perguntas e responder com base em FAQs.
- **Gerenciamento de FAQs**:
  - Adicione FAQs manualmente ou importe via JSON.
  - Exclua FAQs existentes (somente para administradores).
  - Suporte a imagens e arquivos associados às FAQs.
- **Autenticação**:
  - Login seguro para usuários e administradores.
  - Controle de acesso (apenas admins podem gerenciar FAQs).
- **Interface Responsiva**:
  - Design moderno com TailwindCSS.
  - Modo claro/escuro com alternância de tema.
- **Internacionalização**: Suporte a português (pt-BR) no chat e na interface.

## 🚀 Tecnologias Utilizadas
- **Backend**: Flask (Python)
- **Frontend**: HTML, TailwindCSS, JavaScript
- **Banco de Dados**: PostgreSQL (ou SQLite para desenvolvimento local)
- **NLP**: Google Dialogflow para processamento de linguagem natural
- **Hospedagem**: Render (ou qualquer serviço compatível com Flask)
- **Autenticação**: Flask-Login
- **Outras Dependências**:
  - `google-cloud-dialogflow` (para NLP)
  - `SQLAlchemy` (para ORM)
  - `Werkzeug` (para segurança)

## 🛠️ Configuração e Instalação

Siga os passos abaixo para configurar o projeto localmente.

### Pré-requisitos
- Python 3.8 ou superior
- PostgreSQL (ou SQLite para testes locais)
- Conta no Google Cloud para usar o Dialogflow
- Git

### Passo 1: Clonar o Repositório
```bash
git clone https://github.com/seu-usuario/assistente-service-desk.git
cd assistente-service-desk
```

### Passo 2: Criar um Ambiente Virtual
```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

### Passo 3: Instalar Dependências
```bash
pip install -r requirements.txt
```

### Passo 4: Configurar Variáveis de Ambiente
Crie um arquivo `.env` na raiz do projeto e adicione as seguintes variáveis:
```env
SECRET_KEY=sua-chave-secreta-aqui
DATABASE_URL=postgresql://seu-usuario:sua-senha@localhost:5432/service_desk
GOOGLE_APPLICATION_CREDENTIALS=/caminho/para/dialogflow-credentials.json
UPLOAD_FOLDER=uploads
```

- **`SECRET_KEY`**: Uma chave secreta para segurança do Flask.
- **`DATABASE_URL`**: URL do banco de dados (ajuste para SQLite se necessário: `sqlite:///service_desk.db`).
- **`GOOGLE_APPLICATION_CREDENTIALS`**: Caminho para o arquivo de credenciais do Dialogflow (ou o conteúdo do JSON).
- **`UPLOAD_FOLDER`**: Diretório para armazenar arquivos enviados (ex.: PDFs).

### Passo 5: Configurar o Dialogflow
1. Crie um agente no [Dialogflow Console](https://dialogflow.cloud.google.com/).
2. Configure os intents (ex.: `consult_faq`, `saudacao`, `ajuda`) conforme descrito na seção **Configuração do Dialogflow** abaixo.
3. Baixe as credenciais do Google Cloud e configure a variável `GOOGLE_APPLICATION_CREDENTIALS`.

### Passo 6: Inicializar o Banco de Dados
Execute o seguinte comando para criar as tabelas:
```bash
flask shell
>>> from app import db
>>> db.create_all()
>>> exit()
```

### Passo 7: Rodar a Aplicação
```bash
flask run
```
Acesse `http://localhost:5000` no navegador.

## 🌐 Deploy no Render
1. Crie uma conta no [Render](https://render.com).
2. Crie um novo **Web Service** e conecte seu repositório GitHub.
3. Configure as variáveis de ambiente no Render (mesmas do `.env`).
4. Adicione um banco de dados PostgreSQL no Render e atualize `DATABASE_URL`.
5. Faça o deploy e acesse a URL gerada (ex.: `https://seu-app.onrender.com`).

## 🧠 Configuração do Dialogflow
1. Crie um agente chamado `ServiceDeskBot` no Dialogflow.
2. Adicione os seguintes intents:
   - **`consult_faq`**: Para consultar FAQs (ex.: "Como configurar uma impressora?").
     - Entidade: `@keyword` (ex.: "impressora", "Wi-Fi").
   - **`saudacao`**: Para saudações (ex.: "Oi", "Bom dia").
   - **`ajuda`**: Para explicar o que o bot pode fazer (ex.: "Preciso de ajuda").
3. Configure o Webhook (se necessário) apontando para `https://seu-app.onrender.com/webhook`.
4. Baixe as credenciais e configure `GOOGLE_APPLICATION_CREDENTIALS`.

## 📖 Uso
1. **Login**:
   - Acesse `/login` e faça login com um usuário existente (crie um admin manualmente no banco de dados para o primeiro acesso).
2. **Chat**:
   - Na página inicial (`/`), use o chat para fazer perguntas como:
     - "Como configurar uma impressora zebra?"
     - "Oi, tudo bem?"
     - "Preciso de ajuda"
   - O bot responderá com base nos intents do Dialogflow e nas FAQs cadastradas.
3. **Gerenciar FAQs** (somente admins):
   - Acesse `/admin/faq` para adicionar ou importar FAQs.
   - Acesse `/faqs` para visualizar e excluir FAQs.
4. **Importar FAQs**:
   - Use um arquivo JSON no formato:
     ```json
     [
         {
             "category": "Hardware",
             "question": "Como configurar uma impressora zebra?",
             "answer": "Conecte o cabo USB.\nInstale os drivers.\nTeste a impressão.",
             "image_url": "https://example.com/zebra-printer.jpg"
         }
     ]
     ```

## 🤝 Contribuição
Contribuições são bem-vindas! Siga os passos abaixo:
1. Faça um fork do repositório.
2. Crie uma branch para sua feature (`git checkout -b feature/nova-funcionalidade`).
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`).
4. Faça push para a branch (`git push origin feature/nova-funcionalidade`).
5. Abra um Pull Request.

## 📜 Licença
Este projeto está licenciado sob a [MIT License](LICENSE).

---

**Feito com 💡 por [AlexandreCalmon] para ajudar equipes de TI a brilharem!**