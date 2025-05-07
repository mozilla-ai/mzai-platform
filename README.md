# MZAI Platform API (v1 POC)

A proof-of-concept Django REST API for generating and running Kubeflow pipelines via an external (Workflow Composer)[https://github.com/mozilla-ai/workflow-composer] service.  
Workflows are defined by a prompt, materialized as YAML, stored on S3, then executed on Kubeflow Pipelines.  

---

## 🚀 Quickstart

### 1. Clone & Virtualenv
> [!NOTE]
> Ensure you run Python 3.11.8

```bash
git clone https://github.com/mozilla-ai/mzai-platform-api.git
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
DATABASE_URL=postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}SECRET_KEY=<your-django-secret-just-create-a-random-UUID>  
DEBUG=True  

# AWS S3
AWS_ACCESS_KEY_ID=<…>
AWS_SECRET_ACCESS_KEY=<…>
AWS_STORAGE_BUCKET_NAME=<your-bucket-name>



# Kubeflow Pipelines
KFP_API_URL=http://127.0.0.1:8888       # after port-forward svc/ml-pipeline
KFP_AUTH_TOKEN=                         # if your KFP has no auth

# External Workflow Composer URL
WORKFLOW_COMPOSER=http://localhost:8085/api/v1/workflows/    # after running the external server

```

### 4. External Deps


You need Kubeflow Pipelines and Workflow Composer working. For Workflow Composer, please relate to https://github.com/mozilla-ai/workflow-composer.

For KFP, I've got it running locally in kind (but also works with minikube), and I've done the following port forward:

```bash
# API
kubectl port-forward svc/ml-pipeline       8888:8888

# UI (in another terminal)
kubectl port-forward svc/ml-pipeline-ui    8080:80
```

Note: if these commands return the error "No resources found in the default namespace": 

```bash
# check which namespace may have been used, let's say it's myNamespace
kubectl get deploy -A 

# Run the previous commands under that namespace
kubectl port-forward -n myNamespace svc/ml-pipeline       8888:8888
kubectl port-forward -n myNamespace svc/ml-pipeline-ui    8080:80
```


### 5. Start Django

```bash
docker-compose up -d
```
# Interactive superuser prompt
```bash
docker-compose exec web python manage.py createsuperuser
```
Once you start Django, you can login into the admin panel in
[http://localhost:8000/admin](http://localhost:8000/admin) and log in with the superuser you created before. You need to add an [Org](http://localhost:8000/admin/core/org/) to the superuser (as this user is an admin user and it's not suppose to run workflows). After that, you need to go to the users page and add the selected [user](http://localhost:8000/admin/core/customuser/) to the organization



## API Documentation

You can see the docs in [http://localhost:8000/api/v1/docs/](http://localhost:8000/api/v1/docs/)