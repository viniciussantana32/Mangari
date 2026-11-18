# Mangari 📖✨

**Mangari** é uma plataforma web completa para catalogação, organização de biblioteca pessoal, leitura digital unificada de mangás (com suporte a arquivos compactados **ZIP/CBZ** e documentos **PDF**) e gestão administrativa centralizada.

> **Trabalho de Conclusão de Curso (TCC) — Programação de Sistemas**  
> **Instituição:** Senac  
> **Autores:** Vinicius Santana & Eduardo Carvalho

---

## 🎨 Identidade Visual
O projeto adota uma paleta moderna e imersiva com tema escuro nativo:
- **Fundo Principal:** `#0B0B0E`
- **Superfícies & Painéis:** `#121216` e `#19191F`
- **Bordas & Divisores:** `#292930`
- **Texto Principal:** `#F5F5F5` (secundário: `#A1A1AA`)
- **Cores de Destaque:** Laranja Vibrante (`#FF7518` / `#FF8C32`) e Dourado/Amarelo (`#FFB627`)

---

## 🛠️ Stack Tecnológica & Arquitetura Modular

### Backend
- **Python 3.12+ / 3.14+**
- **Flask 3.0.3** (Microframework web)
- **Flask-Login** (Gerenciamento de sessão e autenticação de usuários)
- **Flask-SQLAlchemy 3.1.1** & **SQLAlchemy** (ORM para persistência relacional)
- **Flask-Migrate / Alembic** (Versionamento e migrações de esquema de banco de dados)
- **Flask-WTF / WTForms** (Formulários tipados com proteção contra CSRF)
- **PyMySQL** (Driver MySQL para conexão com XAMPP / MariaDB)
- **ReportLab** (Geração de relatórios analíticos em PDF de alta qualidade)
- **Requests** & **Deep-Translator** (Integrações com GraphQL da AniList, MangaDex e serviços de tradução resiliente)
- **Pytest** (Suíte robusta de testes unitários e de integração com SQLite em memória)

### Frontend
- **HTML5 Semântico & Jinja2** (Templates componibilizados com herança e filtros customizados)
- **CSS3 Moderno** (Variáveis CSS, Flexbox, CSS Grid, animações fluidas e suporte responsivo mobile-first)
- **JavaScript Puro (Vanilla ES6+)** (Busca com autocomplete, carrosséis, leitor em canvas, atalhos de teclado e requisições assíncronas via `fetch`)
- **PDF.js (Mozilla)** (Renderização nativa de páginas de PDF em elementos `<canvas>`)

### Estrutura de Pastas
```text
Projeto final/
├── app/
│   ├── forms/              # Definições de formulários WTForms com validações
│   ├── models/             # Modelos relacionais (User, Manga, Chapter, Comment, etc.)
│   ├── routes/             # Blueprints (admin, auth, main, manga, reader, user, library)
│   ├── services/           # Regras de negócio, relatórios, importação e APIs externas
│   ├── static/             # Folhas de estilo (style.css, reader.css, admin.css) e scripts
│   ├── templates/          # Templates Jinja2 organizados por módulo
│   ├── config.py           # Configurações de ambiente, pool e limites
│   ├── extensions.py       # Instâncias do SQLAlchemy, LoginManager, Migrate e CSRF
│   └── __init__.py         # Application Factory (create_app), filtros Jinja e comandos CLI
├── storage/                # Armazenamento isolado de capítulos fora de static/
├── tests/                  # Suíte completa de testes automatizados com Pytest
├── .env.example            # Template de variáveis de ambiente com valores de exemplo
├── requirements.txt        # Dependências do ecossistema Python
└── run.py                  # Ponto de entrada para execução da aplicação
```

---

## 🔒 Recursos de Segurança & Robustez Técnica

1. **Controle de Acesso Baseado em Papéis (RBAC):**
   - Decorador `@admin_required` que garante acesso exclusivo a rotas administrativas (`/admin` e `/reader/manage`), retornando `403 Forbidden` para usuários convencionais e redirecionando não autenticados para `/auth/login`.
2. **Proteção Contra Força Bruta (Brute-Force Rate Limiting):**
   - Limite de 5 tentativas inválidas de autenticação consecutivas com bloqueio temporário por 2 minutos e mensagens instrutivas ao usuário.
3. **Prevenção de XSS (Cross-Site Scripting):**
   - Sanitização de textos e sinopses vindos de APIs externas (`AniList` e `MangaDex`) com remoção de scripts maliciosos, `<script>`, `<iframe>` e atributos de evento (`onload`, `onerror`).
4. **Proteção contra Path Traversal & Zip Bombs:**
   - Validação estrita de caminhos (`../`), extensões e nomes seguros via `secure_filename`.
   - Limites máximos configurados para uploads, total extraído e quantidade de páginas por capítulo.
5. **Conexões Resilientes com o Banco de Dados:**
   - Configuração de `pool_pre_ping: True` e `pool_recycle: 280` no SQLAlchemy para evitar quedas e erros de timeout (`OperationalError 2013 / 2006`) com MySQL/XAMPP.
6. **Integridade de Contas Administrativas:**
   - O sistema impede a exclusão, bloqueio ou rebaixamento acidental do último administrador ativo da plataforma.
7. **Auditoria Administrativa (AdminLog):**
   - Registro detalhado com autor, data/hora, tipo de ação e entidade em todas as operações de mutação (cadastro, edição, exclusão, moderação e exportação).

---

## 🚀 Instalação e Execução Local

### 1. Clonar ou Baixar o Repositório
Abra o terminal na pasta raiz do projeto.

### 2. Criar e Ativar o Ambiente Virtual (`venv`)
```bash
# Criar ambiente virtual
python -m venv .venv

# Ativação no Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Ou no Prompt de Comando (CMD):
.venv\Scripts\activate.bat

# Ativação no Linux/macOS:
source .venv/bin/activate
```

### 3. Instalar as Dependências
```bash
pip install -r requirements.txt
```

### 4. Configurar as Variáveis de Ambiente
Copie o arquivo `.env.example` para `.env`:
```bash
# Windows:
copy .env.example .env

# Linux/macOS:
cp .env.example .env
```
Abra o arquivo `.env` e configure a conexão com o banco de dados.  
*Exemplo para XAMPP MySQL padrão:*
```env
DATABASE_URL=mysql+pymysql://root:@localhost:3306/mangari_db
```
*(Certifique-se de que o banco de dados `mangari_db` foi criado no phpMyAdmin ou MySQL Workbench).*

### 5. Executar as Migrações do Banco de Dados
```bash
flask db upgrade
```

### 6. Criar ou Promover o Administrador
Cadastre uma conta na tela de registro (`/auth/register`) ou promova um usuário existente via CLI:
```bash
flask make-admin seu_email@exemplo.com
```

### 7. Iniciar a Aplicação
```bash
python run.py
```
Acesse o sistema no navegador em: `http://localhost:5000`

---

## 🧪 Testes Automatizados (Pytest)

A plataforma conta com uma suíte abrangente de testes automatizados executados sobre banco SQLite em memória (`TestingConfig`), garantindo que a base de produção permaneça intocada.

Para rodar todos os testes:
```bash
pytest
```
*Cobertura inclui:*
- Autenticação, registro e rate-limiting de login.
- Controle de permissões (RBAC) e segurança de rotas administrativas.
- Importação de capítulos (ZIP/CBZ e PDF), validação de tipos de arquivo e proteção contra Path Traversal.
- Cadastro e prevenção de duplicidade de mangás via AniList.
- Moderação de comentários, denúncias e regras de exclusão de usuários.
- Exportação de relatórios analíticos em **CSV** e **PDF** via ReportLab.
- Leitor digital (progresso assíncrono de leitura e ordenação natural).

---

## 📄 Licença e Direitos Autorais
Este projeto foi desenvolvido estritamente para fins educacionais e acadêmicos. Todos os direitos sobre as obras e mangás exibidos pertencem aos seus respectivos autores, artistas e editoras.
