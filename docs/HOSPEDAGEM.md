# Backend hospedado e layout fitness — versão para revisão

A aplicação ganhou um backend JavaScript que usa o PostgreSQL/Supabase já configurado. O frontend é compilado para `dist/`, e uma Netlify Function encaminha as chamadas `/api/*` à API. Não há credencial de banco no navegador nem no repositório.

## Estado real

- Código do backend JavaScript e da Netlify Function implementado.
- 56 contratos da aplicação local aprovados contra o novo serviço JavaScript; quatro casos exclusivamente locais/backup SQLite não se aplicam a esta rodada.
- 13 testes de API/gateway aprovados: configuração de admin, autenticação, sessões, CSRF, permissões, isolamento, referências Pix, concorrência, datas e encaminhamento seguro.
- Frontend compilado com TypeScript estrito e assets locais.
- Produção Netlify continua bloqueada. Nenhuma prévia ou aplicação foi publicada por esta alteração.
- A publicação da Edge Function foi recusada pela revisão automática: ela criaria uma API pública ativa no Supabase, em conflito com o pedido anterior de não publicar produção. A recusa foi respeitada. A API ainda não está disponível online.
- Migração `hosted_runtime` aplicada ao banco de teste, sem API pública: metadados de configuração, limites de login e tarefa SQL de expiração/faltas. Cron ativo a cada minuto, auditado e idempotente; política profissional continua desabilitada até configuração explícita.

## Site público e acesso administrativo

O responsável optou por manter o projeto Netlify público. O backend hospedado nunca oferece login administrativo sem senha. `/bootstrap` retorna `available: false`.

Enquanto a senha do admin não estiver definida, a tela oferece configuração inicial com código de implantação de uso único. O servidor guarda apenas o hash desse código, com validade; a senha escolhida recebe hash scrypt. Uma definição válida consome o código e invalida sessões anteriores. Reinícios e novas versões não reabrem esse modo.

Código de implantação, senha e cookies não fazem parte deste arquivo, dos assets ou dos commits. O código de uso único só deve ser entregue ao responsável por canal privado quando a API estiver autorizada e disponível.

## Autenticação da API

A API usa sessões opacas da própria aplicação, autorização por perfil/unidade, CSRF em alterações, cookies HttpOnly/Secure/SameSite e limite persistente de tentativas de login. A Edge Function está preparada para autenticação própria, sem depender do JWT do Supabase; isso exige `verify_jwt: false` na publicação. Rotas de dados exigem sessão; saúde, login e configuração inicial têm validações específicas. A configuração inicial exige o código válido, não o nome admin.

## Próximos passos após autorização explícita

1. Publicar o backend de demonstração no Supabase e testar chamadas HTTP reais.
2. Validar o funcionamento no runtime e os arquivos de log sem expor credenciais.
3. Habilitar uma prévia no Netlify, conservando o bloqueio da produção.
4. Entregar URL de teste e código de configuração ao responsável.
5. Concluir inspeção visual em navegador. O ambiente atual não oferece essa ferramenta.

A antiga versão Python e seus testes continuam disponíveis para execução local. Os limites funcionais do MVP (tutoria de reserva, relatórios avançados e demais itens de STATUS.md) continuam explícitos; esta adaptação não os transforma em funcionalidades concluídas.
