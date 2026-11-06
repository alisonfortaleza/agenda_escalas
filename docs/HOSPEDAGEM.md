# Backend hospedado e layout Panobianco Cassimiro

A aplicação ganhou um backend JavaScript que usa o PostgreSQL/Supabase já configurado. O frontend é compilado para `dist/`, e uma Netlify Function encaminha as chamadas `/api/*` à API. Não há credencial de banco no navegador nem no repositório.

## Implantação de demonstração autorizada

O responsável autorizou explicitamente a publicação no Netlify para testes. O bloqueio anterior de compilação em production foi removido somente após essa autorização. Este contexto de hospedagem serve a demonstração com dados fictícios, não operações financeiras reais.

API Supabase agenda-api publicada com autenticação própria. O frontend e a Netlify Function usam SUPABASE_URL no contexto production, sem credencial privilegiada no navegador. Cron de expiração/faltas permanece ativo no banco de teste.

Validação anterior: 66 testes Python, 56 contratos JavaScript (4 locais ignorados), 13 testes API/gateway. Compilação e testes do gateway são repetidos para a implantação. Conferência visual em navegador ainda depende de ferramenta disponível.

## Site público e acesso administrativo

O responsável optou por manter o projeto Netlify público. O backend hospedado nunca oferece login administrativo sem senha. `/bootstrap` retorna `available: false`.

Enquanto a senha do admin não estiver definida, a tela oferece configuração inicial com código de implantação de uso único. O servidor guarda apenas o hash desse código, com validade; a senha escolhida recebe hash scrypt. Uma definição válida consome o código e invalida sessões anteriores. Reinícios e novas versões não reabrem esse modo.

Código de implantação, senha e cookies não fazem parte deste arquivo, dos assets ou dos commits. O código de uso único só deve ser entregue ao responsável por canal privado quando a API estiver autorizada e disponível.

## Autenticação da API

A API usa sessões opacas da própria aplicação, autorização por perfil/unidade, CSRF em alterações, cookies HttpOnly/Secure/SameSite e limite persistente de tentativas de login. A Edge Function está preparada para autenticação própria, sem depender do JWT do Supabase; isso exige `verify_jwt: false` na publicação. Rotas de dados exigem sessão; saúde, login e configuração inicial têm validações específicas. A configuração inicial exige o código válido, não o nome admin.

## Acesso

URL publicada: https://agenda-e-escalas.netlify.app. Deploy 6aedfcaa80b3048cb00548bf em estado ready. Chamadas HTTP de página, logomarcas, saúde, bootstrap, login, estado, permissões, CSRF e logout aprovadas para os cinco perfis de demonstração.

Perfis fictícios gerente, recepcao, professor, professor2 e estagiario: senha de demonstração Demo@2026!. O admin define a própria senha usando o código de implantação de uso único entregue ao responsável, que não integra o código-fonte.

As limitações funcionais do MVP permanecem descritas em STATUS.md. Hospedagem não transforma os itens pendentes em funcionalidades prontas.
