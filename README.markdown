# 🚀 Plataforma de Aprendizagem Gamificada

Bem-vindo à **Plataforma de Aprendizagem Gamificada**, uma aplicação web interativa projetada para instituições de ensino. O nosso objetivo é tornar a aprendizagem mais envolvente e colaborativa através de um sistema de chatbot inteligente, desafios, equipas e recompensas.

## 📖 Visão Geral

Esta plataforma combina um chatbot para responder a dúvidas dos alunos com um robusto sistema de gamificação. Os alunos podem ganhar pontos, subir de nível, formar equipas para enfrentar desafios complexos ("Boss Fights") e competir em rankings, transformando o processo de aprendizagem numa jornada emocionante.

## 👨‍🎓 Guia do Usuário (Aluno)

Esta secção é para si, aluno! Descubra como tirar o máximo proveito da plataforma.

### 1. Dashboard Principal

Ao fazer login, você será recebido pelo seu Dashboard pessoal. Aqui, você encontra um resumo de tudo o que é importante:

- **Seu Progresso**: Veja o seu nível atual, a sua insígnia e uma barra de XP que mostra o quão perto está de subir de nível.
- **Desafio do Dia**: Fique atento a um desafio especial diário que oferece pontos de bónus!
- **Chatbot**: O seu assistente de IA está sempre pronto para responder às suas perguntas.

### 2. Chatbot Inteligente

Use o chat para pesquisar qualquer tópico relacionado com os seus estudos. O bot irá procurar na nossa base de conhecimento (FAQs) e, se encontrar um desafio relacionado com a sua pesquisa, irá sugeri-lo para você ganhar pontos extra!

### 3. Central de Desafios

Na página de Desafios, você encontrará:

- **Desafios Individuais**: Testes de conhecimento que você pode completar sozinho.
- **Desafios de Time**: Marcados com um ícone especial, estes desafios requerem que você faça parte de uma equipa.
- **Dicas (Hints)**: Se estiver preso num desafio, pode gastar alguns dos seus pontos para desbloquear uma dica útil.

### 4. Times e Colaboração

Na secção de Times, você pode:

- Criar o seu próprio time
- Juntar-se a um time existente
- Ver os detalhes de cada time, incluindo os seus membros e estatísticas
- Enfrentar os **"Boss Fights"**: Desafios épicos com múltiplas etapas que só podem ser derrotados com o trabalho de toda a equipa!

### 5. Ranking

Visite a página de Ranking para ver a sua posição e a da sua equipa. A competição é dividida em:

- **Ranking Individual**: Classificação geral de todos os alunos
- **Ranking de Times**: Veja qual é a equipa com mais pontos

### 6. Perfil e Conquistas

Na sua página de Perfil, você pode:

- **Personalizar o seu avatar** com uma imagem à sua escolha
- **Ver as suas Conquistas**: Uma galeria de "medalhas" que você desbloqueia ao atingir marcos importantes, como completar o seu primeiro desafio ou entrar num time

## 🛡️ Guia do Administrador

Esta secção detalha como gerir todo o conteúdo e os utilizadores da plataforma através do Painel de Administração.

### 1. Dashboard de Administração

O seu ponto de partida, onde tem uma visão geral da plataforma e atalhos para todas as secções de gestão.

### 2. Gestão de Conteúdo

- **Gerenciar FAQs**: Crie, edite e apague as perguntas e respostas que alimentam o chatbot. Você pode adicionar texto, imagens, vídeos e até ficheiros para download.
- **Gerenciar Desafios**: Crie e gira os desafios individuais e de time. Defina a pergunta, a resposta esperada, a recompensa em pontos, o nível necessário e adicione dicas (com um custo em pontos).
- **Gerenciar Trilhas**: Agrupe desafios numa sequência lógica para criar percursos de aprendizagem guiados. Defina a ordem dos desafios e uma recompensa de bónus por completar a trilha.
- **Gerenciar Boss Fights**: Crie os desafios mais complexos da plataforma. Defina o "Boss", as suas múltiplas "Etapas" e as "Tarefas" individuais dentro de cada etapa que os times precisarão de completar.

### 3. Gestão de Gamificação

- **Gerenciar Níveis**: Crie os diferentes níveis que os alunos podem alcançar. Defina os pontos mínimos para cada nível e faça o upload de uma imagem personalizada para a insígnia.
- **Gerenciar Conquistas**: Crie "medalhas" que são atribuídas automaticamente quando os alunos atingem certos marcos (ex: completar 10 desafios, entrar num time).

### 4. Gestão de Utilizadores e Times

- **Gerenciar Utilizadores**: Veja a lista de todos os alunos, o seu progresso e atribua ou remova permissões de administrador.
- **Gerenciar Times**: Monitore todos os times criados na plataforma e, se necessário, dissolva um time.

## 💻 Guia do Desenvolvedor

Esta secção contém as informações técnicas para configurar, executar e contribuir para o projeto.

## 🛠️ Tecnologias Utilizadas

- **Backend**: Python com Flask
- **Base de Dados**: PostgreSQL (produção) / SQLite (desenvolvimento) com SQLAlchemy
- **Frontend**: HTML5, TailwindCSS, JavaScript (com Alpine.js para interatividade)
- **NLP**: spaCy para processamento de linguagem natural no chatbot
- **Armazenamento de Ficheiros**: Cloudinary para upload de imagens (insígnias, avatares, etc.)
- **Cache**: Redis para caching de queries e sessões
- **Deployment**: Configurado para a plataforma Railway

## ⚙️ Configuração do Ambiente Local

### 1. Clonar o Repositório

```bash
git clone <URL_DO_SEU_REPOSITORIO>
cd <NOME_DA_PASTA>
```

### 2. Criar e Ativar um Ambiente Virtual

```bash
python -m venv venv
source venv/bin/activate  # No Windows: venv\Scripts\activate
```

### 3. Instalar as Dependências

```bash
pip install -r requirements.txt
```

### 4. Descarregar o Modelo de Linguagem

```bash
python -m spacy download pt_core_news_sm
```

### 5. Configurar Variáveis de Ambiente

Crie um ficheiro `.env` na raiz do projeto. Para um ambiente de desenvolvimento local simples, você pode usar SQLite.

```env
SECRET_KEY=uma-chave-secreta-muito-segura
DATABASE_URL=sqlite:///service_desk.db

# As credenciais do Cloudinary são opcionais para o desenvolvimento local,
# mas necessárias para o upload de imagens.
CLOUDINARY_CLOUD_NAME=seu_cloud_name
CLOUDINARY_API_KEY=sua_api_key
CLOUDINARY_API_SECRET=seu_api_secret
```

### 6. Inicializar a Base de Dados

A aplicação irá criar a base de dados SQLite e as tabelas automaticamente na primeira vez que for executada.

### 7. Criar um Utilizador Administrador

Use o comando CLI personalizado para criar a sua conta de administrador:

```bash
flask create-admin --name "Seu Nome" --email "admin@exemplo.com" --password "sua_senha"
```

### 8. Executar a Aplicação

```bash
flask run
```

A aplicação estará disponível em `http://127.0.0.1:5000`.

## 🚀 Deploy (Railway)

O projeto está configurado para deploy contínuo no Railway. Simplesmente faça `git push` para o seu repositório do GitHub conectado ao Railway, e a plataforma irá construir e fazer o deploy da nova versão automaticamente. As variáveis de ambiente (como `DATABASE_URL`, `REDIS_URL` e as do Cloudinary) devem ser configuradas diretamente na interface do Railway.

---

## 📄 Licença

Este projeto está licenciado sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

## 🤝 Contribuições

Contribuições são bem-vindas! Por favor, abra uma issue ou envie um pull request com suas sugestões.

## 📞 Suporte

Para dúvidas ou suporte, entre em contato através do email: suporte@exemplo.com