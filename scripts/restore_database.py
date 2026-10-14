from pathlib import Path
import subprocess

container_name = "machado-fintech-api_db"

database = "machadoFintech"
user = "machadoFintech"
password = "machadoFintech"

dump_file = Path("./migrations/backup_db.dump")

if not dump_file.exists():
    raise FileNotFoundError(f"Arquivo '{dump_file}' não encontrado.")

command = [
    "docker",
    "cp",
    dump_file,
    f"{container_name}:/tmp/backup.dump",
]

subprocess.run(command, check=True)

restore_command = [
    "docker",
    "exec",
    "-e",
    f"PGPASSWORD={password}",
    container_name,
    "pg_restore",
    "-U",
    user,
    "-d",
    database,
    "--clean",
    "--if-exists",
    "/tmp/backup.dump",
]
try:
    subprocess.run(restore_command, check=True)
    print(f"Banco de dados restaurado com sucesso a partir de: {dump_file}")
finally:
    subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "rm",
            "-f",
            "/tmp/backup.dump",
        ],
        check=True,
    )
    print("Arquivo temporário removido do container.")