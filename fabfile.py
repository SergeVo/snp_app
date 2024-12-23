import subprocess
from fabric import Connection, task

# Конфигурация сервера
REMOTE_HOST = "94.228.125.223"  # IP вашего VPS
REMOTE_USER = "root"           # Пользователь на сервере
REMOTE_DIR = "/var/www/snpapp"  # Путь до папки проекта на сервере
LOCAL_PROJECT_DIR = r"D:\snp_app"  # Локальный путь до проекта (Windows)
GIT_REPO = "git@github.com:SergeVo/snp_app.git"  # Репозиторий с проектом
PROJECT_NAME = "snp_app"  # Название проекта


@task
def deploy(c):
    # Подключение к серверу
    conn = Connection(host=REMOTE_HOST, user=REMOTE_USER)

    print("1. Проверка и установка необходимых пакетов...")
    required_packages = ["python3-pip", "python3-venv", "nginx", "git"]
    for package in required_packages:
        result = conn.run(f"dpkg -l | grep -qw {package}", warn=True)
        if result.failed:
            print(f"Пакет {package} не установлен. Устанавливаем...")
            conn.run(f"sudo apt install -y {package}")
        else:
            print(f"Пакет {package} уже установлен.")

    print("2. Клонирование или обновление проекта...")
    if conn.run(f"test -d {REMOTE_DIR}", warn=True).failed:
        conn.run(f"git clone {GIT_REPO} {REMOTE_DIR}")
    else:
        with conn.cd(REMOTE_DIR):
            conn.run("git pull origin main")

    print("3. Настройка виртуального окружения...")
    with conn.cd(REMOTE_DIR):
        if conn.run("test -d venv", warn=True).failed:
            conn.run("python3 -m venv venv")
        conn.run("venv/bin/pip install -r requirements.txt")

    print("4. Применение миграций...")
    with conn.cd(REMOTE_DIR):
        conn.run("venv/bin/python manage.py migrate")

    print("5. Сборка статических файлов...")
    with conn.cd(REMOTE_DIR):
        conn.run("venv/bin/python manage.py collectstatic --noinput")

    print("6. Настройка Gunicorn...")
    gunicorn_service = f"""
    [Unit]
    Description=Gunicorn instance to serve {PROJECT_NAME}
    After=network.target

    [Service]
    User={REMOTE_USER}
    Group=www-data
    WorkingDirectory={REMOTE_DIR}
    ExecStart={REMOTE_DIR}/venv/bin/gunicorn --workers 3 --bind unix:{REMOTE_DIR}/{PROJECT_NAME}.sock {PROJECT_NAME}.wsgi:application

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
            root {REMOTE_DIR};
        }}

        location / {{
            include proxy_params;
            proxy_pass http://unix:{REMOTE_DIR}/{PROJECT_NAME}.sock;
        }}
    }}
    """
    conn.run(f"echo '{nginx_config}' | sudo tee /etc/nginx/sites-available/{PROJECT_NAME}")
    conn.run(f"sudo ln -s /etc/nginx/sites-available/{PROJECT_NAME} /etc/nginx/sites-enabled")
    conn.run("sudo nginx -t")
    conn.run("sudo systemctl restart nginx")

    print("8. Завершение настройки безопасности...")
    conn.run("sudo ufw allow 'Nginx Full'")  # Открываем доступ к Nginx
    conn.run("sudo ufw enable")

    print("Деплой завершён!")


@task
def prepare(c):
    print("Подготовка локального репозитория...")
    try:
        subprocess.run(
            f"cd {LOCAL_PROJECT_DIR} && git add . && git commit -m 'Автодеплой' && git push origin main",
            shell=True,
            check=True
        )
        print("Локальный репозиторий успешно подготовлен.")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка при подготовке локального репозитория: {e}")
