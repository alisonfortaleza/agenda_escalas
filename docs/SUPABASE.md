# Adaptação para Supabase / PostgreSQL

Estado: adaptador testado em PostgreSQL local; migração aplicada ao projeto novo `Agenda e Escalas Project` e dados fictícios inicializados. O sistema de estoque não foi alterado. Consulte `INFRAESTRUTURA.md` para a configuração atual e as pendências de hospedagem.

## O que foi preparado

- `app/postgres.py` mantém a API semântica e o frontend, usando psycopg 3.2.13 com versões fixadas.
- Migração criada pelo comando oficial `supabase migration new prisma_agenda_private`, usando CLI 3.0.0 e diretório de estado local.
- Esquema `prisma_agenda` privado, sem grants para o navegador/Data API. Não são criadas tabelas no `public` do estoque.
- RLS com contexto transacional de organização e unidade; papel de execução sem superusuário ou bypass de RLS. A API autentica a sessão e estabelece o contexto validado antes de consultar as entidades.
- Tabelas internas de usuários/sessões permitem autenticação pré-contexto somente ao papel privado de backend. Não estão disponíveis a `anon`/`authenticated` do Supabase. Nenhuma autorização usa `user_metadata` editável.
- Restrições de exclusão GiST garantem intervalo semiaberto por sala, profissional e tutor. Vínculos compostos impedem relacionar registros entre unidades/organizações.
- Serialização transacional por advisory lock conserva a consistência de bloqueios, benefícios, pagamento e reservas entre processos de API. Não há chamada bancária externa dentro de transações.
- Datas absolutas ficam em TIMESTAMPTZ; regras civis continuam calculadas no fuso da unidade.
- Motor de escalas carrega dados uma vez por proposta e valida os candidatos em memória, dentro da mesma transação, evitando milhares de consultas ao banco hospedado.
- Workflow de testes preparado em `.github/workflows/test.yml`, sem etapas de implantação ou segredos de produção.

## Destino ainda necessário

A conta conectada possui uma organização “Panobianco Cassimiro”, um projeto com tabelas de estoque e o repositório privado `panobiancocassimiro-473/panobianco-cassimiro-estoque`.

Recomendação: projeto Supabase e repositório GitHub privados separados para agenda. Não foram criados, cobrados ou alterados recursos remotos nesta etapa. Criar projeto/branch Supabase exige consultar a cotação da organização selecionada e obter concordância para qualquer valor não zero. A autorização para usar GitHub/Supabase não equivale a autorizar alteração do estoque ou publicação de produção.

## Executar localmente com PostgreSQL

O servidor HTTP continua limitado ao loopback. Esta adaptação não habilita hospedagem remota.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-postgres.txt
```

Configure `DATABASE_URL` somente no ambiente do processo do servidor. Para um banco local descartável, a URL deve apontar à instância que você criou; para Supabase, use conexão/pooler fornecido pelo painel e TLS com verificação de certificado. Não coloque a URL em variável pública do frontend, commit, arquivo de demonstração ou mensagem de chat.

Na primeira inicialização de um banco novo explicitamente escolhido:

```bash
APP_ENV=local MIGRATE_ON_START=1 SEED_DEMO=1 BOOTSTRAP_LOCAL=1 .venv/bin/python -m app.server
```

Em reinícios, deixe `MIGRATE_ON_START=0` e `SEED_DEMO=0`; migração e seed não são executados por requisição HTTP. O seed é transacional, não apaga senha e não recria o modo inicial. Configure credencial de migração separadamente do acesso rotineiro. O backend reduz o papel ativo para `prisma_agenda_runtime`. Um login de banco dedicado membro somente desse papel é recomendado para operação; credencial de migração não deve ser usada para servir requisições.

Sem DATABASE_URL, `./run-local.sh` continua usando SQLite.

## Testes PostgreSQL

`tests/run_postgres_contract.py` só aceita endereço loopback e cria um banco aleatório por teste. Recusa URL de Supabase/host remoto para impedir executar a suíte destrutiva de teste em dados hospedados. O usuário PostgreSQL de teste precisa de CREATE DATABASE; cada banco é descartado ao fim do teste. Esses privilégios não são necessários para o servidor da aplicação.

```bash
PRISMA_PG_TEST_URL=postgresql://postgres@127.0.0.1:55432/postgres \
.venv/bin/python tests/run_postgres_contract.py
```

O workflow GitHub usa serviço Postgres 17 efêmero, sem conexão com Supabase. Os contratos de backup de arquivo SQLite são excluídos da rodada PostgreSQL; backup/restauração PostgreSQL exigem pg_dump/pg_restore e homologação no ambiente de destino. Não se considera restaurado um backup Postgres só porque os testes de SQLite passaram.

## Banco e autenticação

A adaptação preserva a autenticação existente (hash scrypt, sessões do servidor e definição de senha do admin) para manter as regras já testadas. Não criou usuários no Supabase Auth, não alterou configuração de login do estoque e não enviou convites/e-mails. Integração opcional com Supabase Auth ainda requer projeto separado/configurado e mapeamento de perfis por organização/unidade.

O acesso inicial sem senha continua permitido apenas no servidor local explicitamente protegido. Para hospedagem no Sites será preciso um backend compatível com o runtime, a proteção autenticada da implantação e configuração de segredos. Uma chave publicável de Supabase, sozinha, não protege um botão admin nem substitui esse fluxo.

## Limites atuais

Ainda não há site hospedado dentro do ChatGPT. Faltam destino confirmado, criação/configuração dos recursos, publicação privada autorizada, adaptação final do backend ao host e testes de integração nesse ambiente. O adaptador Python não pode ser enviado diretamente ao runtime JavaScript do Sites. Não foi reclassificado um deploy como “teste” para contornar a proibição de publicação.

O comando de preparação de produção continua bloqueando essa versão até a revisão dos requisitos. Arquivos STATUS.md e PUBLICACAO.md continuam registrando as demais pendências do produto.
