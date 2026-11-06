"""Offline restore; online backup via SQLite backup API. No automatic upload."""
import argparse,sqlite3,os,tempfile
from pathlib import Path
from .db import Database,ROOT
from .domain import require

def restore(backup,target):
    source=Path(backup).resolve();target=Path(target).resolve()
    require(source!=target and source.is_file(),'Escolha backup existente e destino diferente.')
    with sqlite3.connect(f'file:{source}?mode=ro',uri=True) as c:
        require(c.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Backup corrompido.')
        require(not c.execute('PRAGMA foreign_key_check').fetchall(),'Backup com referências inválidas.')
        require(c.execute('SELECT version FROM schema_version').fetchone()[0]==1,'Versão de esquema incompatível.')
        target.parent.mkdir(parents=True,exist_ok=True)
        require(not target.exists(),'Destino já existe. Pare o servidor e mova o banco anterior para um arquivo de segurança antes de restaurar.')
        with sqlite3.connect(target) as out: c.backup(out)
    # Never revive sessions from a snapshot.
    with sqlite3.connect(target) as c: c.execute('DELETE FROM sessions');c.commit()

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['backup','restore','check-production']);p.add_argument('file',nargs='?');p.add_argument('--database',default=str(ROOT/'data/agenda.sqlite'));a=p.parse_args()
    if a.action=='check-production':
        print('BLOQUEADO: versão local. Faltam adaptador de hospedagem Sites, TLS/identidade, recuperação segura, revisão das pendências e teste visual.');raise SystemExit(1)
    require(a.file,'Informe o caminho do arquivo.')
    if a.action=='backup':
        require(Path(a.database).exists(),'Banco de origem inexistente.');require(not Path(a.file).exists(),'Arquivo de destino já existe.');Database(a.database).backup(a.file)
    else: restore(a.file,a.database)
    print('Operação concluída. Arquivo local; nenhum upload realizado.')
if __name__=='__main__':main()
