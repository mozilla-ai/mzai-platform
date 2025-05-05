# MZAI Platform API (v1 POC)

A proof-of-concept Django REST API for generating and running Kubeflow pipelines via an external “Gardener” service.  
Workflows are defined by a prompt, materialized as YAML, stored on S3, then executed on Kubeflow Pipelines.  

---

## 🚀 Quickstart

### 1. Clone & Virtualenv
> [!NOTE]
> Ensure you run Python 3.11.8

```bash
git clone https://github.com/your-org/mzai-platform-api.git
cd mzai-platform-api
pyenv shell 3.11.8
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Copy `.env.example` into `.env` and fill in

```dotenv
# Django & DB
DATABASE_URL=sqlite:///db.sqlite3  
SECRET_KEY=<your-django-secret-just-create-a-random-UUID>  
DEBUG=True  

# AWS S3
AWS_ACCESS_KEY_ID=<…>
AWS_SECRET_ACCESS_KEY=<…>
AWS_STORAGE_BUCKET_NAME=<your-bucket-name>

# Gardener callback - Where the gardener will post the YAML for the workflow. by default localhost:8000
CALLBACK_BASE_URL=http://localhost:8000

# Kubeflow Pipelines
KFP_API_URL=http://127.0.0.1:8888       # after port-forward svc/ml-pipeline
KFP_AUTH_TOKEN=                         # if your KFP has no auth

# External Gardener
GARDENER_URL=http://localhost:8001      # after running the mock server

```
### 4. Database Setup
Run the migrations and add a superuser to your database so you can run things inside the app

```bash
python manage.py migrate
python manage.py createsuperuser --email admin@example.com
```


### 5. External Deps


You need Kubeflow Pipelines and Gardener working. For gardener, please relate to https://github.com/mozilla-ai/workflow-composer.

For KFP, I've got it running locally in kind , and I've done the following port forward:

```bash
# API
kubectl port-forward svc/ml-pipeline       8888:8888

# UI (in another terminal)
kubectl port-forward svc/ml-pipeline-ui    8080:80
```


### 6. Start Django

```bash
docker-compose up
```

Once you start Django, you can login into the admin panel in
[http://localhost:8000/admin](http://localhost:8000/admin) and log in with the superuser you created before. You need to add an [Org](http://localhost:8000/admin/core/org/) to the superuser (as this user is an admin user and it's not suppose to run workflows). After that, you need to go to the users page and add the selected [user](http://localhost:8000/admin/core/customuser/) to the organization

## API Documentation

You can see the docs in [http://localhost:8000/api/v1/docs/](http://localhost:8000/api/v1/docs/)