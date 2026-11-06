# Infraestrutura da demonstração — 06/11/2026

GitHub: alisonfortaleza/agenda_escalas, main, conectado ao Netlify. Projeto agenda-e-escalas, equipe Aj Personal Trainer, id beb6b7c2-f23b-4861-8ac5-6b47a6961d16.

URL publicada: https://agenda-e-escalas.netlify.app. Deploy 6aedfcaa80b3048cb00548bf, estado ready, commit a4165d75a7311c5797a093b5d319ed6382b81d10.

Supabase: Agenda e Escalas Project, ref qgoqpvshqirczealwiyc. API agenda-api v1 ativa; PostgreSQL com schema privado prisma_agenda, RLS e conflitos transacionais. Rotas de dados validam sessões próprias; a Edge Function não depende do JWT Supabase. Gateway Netlify usa SUPABASE_URL configurada em production; não há credencial de banco no navegador. Migrações 20261106145458 e 20261106154854 aplicadas, dados fictícios inicializados e cron de expiração/faltas ativo.

O projeto Netlify permanece público conforme a preferência do responsável. Admin sem senha está desativado. A configuração de senha inicial exige código de uso único, guardado apenas como hash privado no banco. Credenciais, cookies, bancos, backups e códigos de ativação não integram o repositório público. A especificação original anexada não foi enviada ao GitHub.

Publicação autorizada expressamente pelo responsável após a fase local. Nenhuma movimentação financeira real. Recursos prontos e pendentes em STATUS.md.
