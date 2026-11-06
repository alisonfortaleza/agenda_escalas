# Infraestrutura da agenda — configuração de 06/11/2026

## Recursos selecionados pelo responsável

- GitHub: `alisonfortaleza/agenda_escalas`, branch `main`.
- Netlify: `agenda-e-escalas`, equipe `Aj Personal Trainer` / `alisonfortaleza`.
- Projeto Netlify: `beb6b7c2-f23b-4861-8ac5-6b47a6961d16`.
- Supabase: `Agenda e Escalas Project`, ref `qgoqpvshqirczealwiyc`.
- URL da API: `https://qgoqpvshqirczealwiyc.supabase.co`.

Estes identificadores e a URL são públicos; credenciais de acesso não pertencem ao repositório.

## Concluído

Migração inicial `20261106145458_prisma_agenda_private.sql` aplicada ao Supabase separado da agenda. A versão local foi alinhada à versão registrada pela ferramenta no histórico remoto, mantendo o SQL idêntico. São 21 tabelas com RLS no schema privado `prisma_agenda`, sem USAGE para `anon` ou `authenticated`, e constraints de intervalo/relacionamento. A checagem de segurança do projeto não retornou alertas após a migração.

Dados fictícios inicializados uma única vez: organizações/unidades/salas, equipe, alunos, profissionais externos, tutoria, jornadas e contas de demonstração da aplicação. Nenhum usuário foi criado em Supabase Auth e nenhum convite foi enviado. Não foram geradas cobranças, reservas ou pagamentos reais. As contas ainda não têm uma API hospedada para login; o admin sem senha continua limitado ao ambiente local protegido.

No Netlify, `SUPABASE_URL` e `SUPABASE_PUBLISHABLE_KEY` foram configuradas somente no contexto `deploy-preview`. São dados não secretos. O plano atual recusou escopos granulares; por isso usam os escopos padrão, sem disponibilização à produção. Não há `service_role`, senha administrativa de Postgres ou DATABASE_URL no frontend, no repositório ou nas variáveis aqui configuradas.

`netlify.toml` usa `ignore = "exit 0"` para cancelar builds automáticos. O comando de build também recusa publicar a aplicação enquanto o backend local não estiver adaptado. `.netlify/` fica ignorado pelo Git.

## Vínculo GitHub → Netlify

A integração conectada oferece criação de projeto, variáveis e consultas, mas não expõe a vinculação de repositório. A alternativa pela API direta requer autenticação adicional e respondeu 401; não foi solicitado token em chat.

Para concluir o vínculo na interface do Netlify:

1. Abra https://app.netlify.com/projects/agenda-e-escalas.
2. Entre em **Project configuration → Build & deploy → Continuous deployment → Repository** (o menu pode aparecer como **Developer settings**).
3. Escolha **Link repository / Link to a Git repository → GitHub**.
4. Use a conta **alisonfortaleza** e selecione **agenda_escalas**, branch **main**.
5. Se o repositório não aparecer, use **Configure Netlify on GitHub** e permita acesso somente ao repositório da agenda.

A configuração versionada mantém os builds bloqueados. Não habilite publicação automática até a adaptação e validação do backend. O projeto Netlify foi criado sem uma aplicação publicada.

## Próxima etapa técnica

O backend atual é Python, executado localmente, com adaptadores SQLite e PostgreSQL. Netlify Functions exige adaptar o runtime; conectar GitHub e indicar Supabase não realiza essa adaptação automaticamente. Não se deve publicar apenas o frontend simulando que a API está pronta.

Depois da adaptação, configurar credenciais restritas somente no runtime do servidor e comprovar conexão transacional; testar todos os perfis no ambiente protegido. Somente liberar admin de implantação sem senha quando a proteção externa estiver confirmada. Na consulta mais recente, o Netlify não informou senha ou SSO ativos; isso exige revisão antes de qualquer acesso administrativo remoto temporário.

O repositório é público. A especificação original anexada permanece no ambiente de trabalho e não é incluída no envio ao GitHub; não inserir dados de alunos reais, segredos, bancos, backups ou sessões no repositório.
