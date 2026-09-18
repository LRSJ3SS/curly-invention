# UABE Python - Render Edition

Versão otimizada para hospedagem no **Render.com**. Extraia Unity Asset Bundles diretamente na nuvem.

## 🚀 Deploy no Render (5 minutos)

### Opção A: Deploy Manual (recomendado)

1. **Crie um repositório GitHub** com todos estes arquivos
2. Acesse [render.com](https://render.com) e faça login com GitHub
3. Clique em **New → Web Service**
4. Selecione seu repositório
5. Preencha as configurações:

| Campo | Valor |
|-------|-------|
| **Name** | `uabe-python` (ou o que quiser) |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT` |
| **Instance Type** | `Free` |

6. Clique em **Deploy**
7. Aguarde 2-5 minutos para o build e inicialização
8. Sua aplicação estará em: `https://SEU-APP.onrender.com`

### Opção B: Usando Blueprint (render.yaml)

1. Edite o arquivo `render.yaml` e altere a URL do repositório
2. No Render: **New → Blueprint**
3. Conecte o repositório e siga as instruções

---

## 📋 Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `app.py` | Aplicação Flask adaptada para o Render |
| `uabe_py.py` | Módulo de extração UnityPy |
| `requirements.txt` | Dependências (inclui gunicorn) |
| `templates/index.html` | Interface web |
| `render.yaml` | Configuração Blueprint (opcional) |

---

## ⚙️ Ajustes importantes para o Render

### 🔌 Porta e Host
- A porta é lida da variável de ambiente `$PORT` (o Render atribui automaticamente)
- Host configurado como `0.0.0.0` (obrigatório para receber conexões externas)

### 🐍 Gunicorn
- Usamos `gunicorn` como servidor WSGI de produção
- 2 workers, 4 threads cada, timeout de 120s (para extrações maiores)
- **Aviso**: No plano gratuito, cada worker é uma instância separada — se 2 requisições forem para workers diferentes, o arquivo carregado em um não estará disponível no outro. Para uso pessoal/simples isso raramente é problema.

### 💾 Sistema de arquivos efêmero
- O Render **não mantém arquivos** entre reinícios/deploys
- Arquivos enviados e extraídos são temporários
- A cada novo deploy ou "acordar" do sleep, tudo é limpo automaticamente

### 😴 Sleep no plano gratuito
- A aplicação dorme após **15 minutos** sem requisições
- Primeiro acesso após dormir: ~20-30 segundos para acordar
- Solução: use serviços como [UptimeRobot](https://uptimerobot.com) para fazer ping a cada 10min e manter acordada

### 📦 Limite de upload
- Render tem limite de **~100MB** por requisição no plano gratuito
- Para arquivos maiores, considere upgrade de plano ou hospedagem própria

---

## 🔗 API Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Interface web |
| GET | `/api/health` | Health check |
| POST | `/api/upload` | Upload de arquivo Unity |
| GET | `/api/assets` | Lista assets (params: `type`, `search`) |
| GET | `/api/types` | Tipos de assets presentes |
| GET | `/api/summary` | Resumo do bundle |
| GET | `/api/asset/<id>` | Detalhes de um asset |
| GET | `/api/preview/<id>` | Preview PNG de textura |
| GET | `/api/extract/<id>` | Download de asset individual |
| POST | `/api/extract-all` | Extração em lote → retorna ZIP |
| POST | `/api/unload` | Descarrega arquivo |

---

## 🧪 Teste local

```bash
pip install -r requirements.txt
python app.py
# Acesse: http://localhost:5000
```

---

## 📝 Notas

- **CORS** está habilitado para `*.github.io` e `*.onrender.com` — você pode usar a interface do GitHub Pages conectada a este backend se quiser
- Para produção com muitos usuários, considere upgrade para plano pago e use Redis para compartilhar estado entre workers
- O UnityPy funciona melhor com bundles de Unity 5.x até versões recentes (2020+)
