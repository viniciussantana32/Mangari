import os
import sys
import shutil
import subprocess
import webbrowser
import time

def run(cmd, env=None):
    print(f"\n> Executando: {' '.join(cmd)}")
    res = subprocess.run(cmd, env=env)
    if res.returncode != 0:
        print(f"\n[ERRO] Falha ao executar: {' '.join(cmd)}")
        input("Pressione ENTER para sair...")
        sys.exit(1)

def main():
    base_dir = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
    os.chdir(base_dir)

    print("==========================================")
    print("   INSTALADOR AUTOMATICO - MANGARI        ")
    print("==========================================")

    venv_dir = os.path.join(base_dir, ".venv")
    venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
    venv_flask = os.path.join(venv_dir, "Scripts", "flask.exe")

    if not os.path.exists(venv_python):
        print("\n[1/5] Criando ambiente virtual (.venv)...")
        run(["python", "-m", "venv", ".venv"])
    else:
        print("\n[1/5] Ambiente virtual (.venv) ja existe.")

    print("\n[2/5] Instalando dependencias do requirements.txt...")
    run([venv_python, "-m", "pip", "install", "-r", "requirements.txt"])

    env_file = os.path.join(base_dir, ".env")
    env_example = os.path.join(base_dir, ".env.example")
    if not os.path.exists(env_file) and os.path.exists(env_example):
        print("\n[3/5] Criando arquivo .env a partir do .env.example...")
        shutil.copyfile(env_example, env_file)
    else:
        print("\n[3/5] Arquivo .env ja configurado.")

    print("\n[4/5] Criando banco mangari_db (MySQL) e rodando migrations...")
    create_db_code = (
        "import pymysql; "
        "conn = pymysql.connect(host='localhost', user='root', password=''); "
        "conn.cursor().execute('CREATE DATABASE IF NOT EXISTS mangari_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;'); "
        "conn.close(); "
        "print('Banco mangari_db verificado/criado com sucesso!')"
    )
    run([venv_python, "-c", create_db_code])
    run([venv_flask, "db", "upgrade"])

    admin_email = input("\nDigite um e-mail para promover a admin (ou ENTER para pular): ").strip()
    if admin_email:
        subprocess.run([venv_flask, "make-admin", admin_email])

    print("\n[5/5] Iniciando o servidor Mangari em http://localhost:5000 ...")
    time.sleep(1)
    webbrowser.open("http://localhost:5000")
    run([venv_python, "run.py"])

if __name__ == "__main__":
    main()
