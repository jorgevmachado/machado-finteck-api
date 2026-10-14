import subprocess

container_name = "machado-fintech-api_db"

database = "machadoFintech"
user = "machadoFintech"
password = "machadoFintech"

output_file = "./migrations/backup_db.dump"

command = [
    "docker",
    "exec",
    "-e",
    f"PGPASSWORD={password}",
    container_name,
    "pg_dump",
    "-U",
    user,
    "-Fc",
    database,
]

with open(output_file, "wb") as f:
    subprocess.run(command, stdout=f, check=True)

print(f"Dump gerado com sucesso em: {output_file}")