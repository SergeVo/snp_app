from fabric import Connection, task


# Конфигурация сервера
REMOTE_HOST = "94.228.125.223"
REMOTE_USER = "root"
REMOTE_DIR = "/var/www/snp_app"          # Базовая директория
PROJECT_DIR = f"{REMOTE_DIR}/snp"   # Директория с manage.py
GIT_REPO = "git@github.com:SergeVo/snp_app.git"
PROJECT_NAME = "snp_app"
REMOTE_PASSWORD = "fcf6XkyuA3-#HJ"


@task
def deploy(c):
    conn = Connection(
        host=REMOTE_HOST,
        user=REMOTE_USER,
        connect_kwargs={"password": REMOTE_PASSWORD}
    )

    print("1. Проверка и установка пакетов...")
    required_packages = ["python3-pip", "python3-venv", "nginx", "git"]
    for package in required_packages:
        result = conn.run(f"dpkg -l | grep -qw {package}", warn=True)
        if result.failed:
            conn.run(f"sudo apt install -y {package}")

    print("2. Клонирование проекта...")
    if conn.run(f"test -d {REMOTE_DIR}", warn=True).failed:
        conn.run(f"mkdir -p {REMOTE_DIR}")
    conn.run(f"rm -rf {REMOTE_DIR}/*")
    conn.run(f"git clone {GIT_REPO} {REMOTE_DIR}")

    print("3. Настройка виртуального окружения...")
    with conn.cd(PROJECT_DIR):
        if conn.run("test -d venv", warn=True).failed:
            conn.run("python3 -m venv venv")
        conn.run("venv/bin/pip install -r requirements.txt")

    print("4. Применение миграций...")
    with conn.cd(PROJECT_DIR):
        conn.run("venv/bin/python manage.py migrate")

    print("5. Сборка статических файлов...")
    with conn.cd(PROJECT_DIR):
        conn.run("venv/bin/python manage.py collectstatic --noinput")

    print("6. Настройка Gunicorn...")
    gunicorn_service = f"""
    [Unit]
    Description=Gunicorn instance for {PROJECT_NAME}
    After=network.target

    [Service]
    User={REMOTE_USER}
    Group=www-data
    WorkingDirectory={PROJECT_DIR}
    ExecStart={PROJECT_DIR}/venv/bin/gunicorn --workers 3 --bind unix:{PROJECT_DIR}/{PROJECT_NAME}.sock {PROJECT_NAME}.wsgi:application

    [Install]
    WantedBy=multi-user.target
    """
    conn.run(f"echo '{gunicorn_service}' | sudo tee /etc/systemd/system/{PROJECT_NAME}.service")
    conn.run("sudo systemctl daemon-reload")
    conn.run(f"sudo systemctl enable {PROJECT_NAME}")
    conn.run(f"sudo systemctl start {PROJECT_NAME}")

    print("7. Настройка Nginx...")
    nginx_config = f"""
    server {{
        listen 80;
        server_name {REMOTE_HOST};

        location = /favicon.ico {{ access_log off; log_not_found off; }}
        location /static/ {{
            root {PROJECT_DIR};
        }}

        location / {{
            include proxy_params;
            proxy_pass http://unix:{PROJECT_DIR}/{PROJECT_NAME}.sock;
        }}
    }}
    """
    conn.run(f"echo '{nginx_config}' | sudo tee /etc/nginx/sites-available/{PROJECT_NAME}")
    conn.run(f"sudo ln -sf /etc/nginx/sites-available/{PROJECT_NAME} /etc/nginx/sites-enabled")
    conn.run("sudo nginx -t")
    conn.run("sudo systemctl restart nginx")

    print("8. Настройка firewall...")
    conn.run("sudo ufw allow 'Nginx Full'")
    conn.run("sudo ufw enable")

    print("Деплой завершён!")

@task
def prepare(c):
    print("Подготовка локального репозитория...")
    c.local(f"cd {LOCAL_PROJECT_DIR} && git add . && git commit -m 'Автодеплой' && git push origin main")