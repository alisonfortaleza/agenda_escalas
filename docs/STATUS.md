# Estado da entrega local

A especificação anexada contém o escopo de produto e os critérios de aceite. A solicitação desta etapa autoriza desenvolvimento e teste locais, dados fictícios e Pix manual, **sem produção**. Instruções de publicação presentes no anexo não foram tomadas como autorização para publicar.

## Adaptação de hospedagem e visual — 06/11/2026

Backend JavaScript, gateway Netlify e configuração de admin por código de uso único implementados e testados localmente. Site público preservado; admin sem senha desativado na versão hospedada. Layout fitness aplicado ao login e painel. Publicação da API recusada pela revisão automática e pendente de autorização explícita. Detalhes em `HOSPEDAGEM.md` e `DESIGN.md`.

## Atualização de infraestrutura — 06/11/2026

Banco privado aplicado e inicializado no novo Supabase da agenda; repositório GitHub preparado e Netlify configurado sem builds/publicação automáticos. Consulte `INFRAESTRUTURA.md` para o vínculo GitHub/Netlify e a adaptação do backend que ainda faltam. Os limites funcionais listados abaixo continuam vigentes.

## Adaptação posterior para Supabase / GitHub

Adaptador PostgreSQL e migração privados preparados, com isolamento no banco, conflitos de intervalo e CI localizável em `.github/workflows/test.yml`. Validação em Postgres descartável local; nenhum banco/repositório remoto modificado. Destino e hospedagem continuam pendentes. Detalhes em `SUPABASE.md`.

## Implementado e testável

- Frontend TypeScript com compilação estrita, layout responsivo, login, dashboard, agenda diária/semanal, detalhes, cadastros, financeiro, escalas, permutas, configuração e auditoria.
- Backend HTTP com operações semânticas e SQLite em WAL, migração e transações `BEGIN IMMEDIATE`. A serialização inclui reserva, profissional, tutor, benefício e bloqueio; verificações de intervalo completo, com fim excluído.
- Organização, unidade e sala separadas, isolamento no servidor, seleção de unidade só para admin, limpeza de formulários/cache na troca e descarte de respostas antigas. Outra aba conserva seu contexto por requisição.
- Admin local temporário sem senha, explicitamente habilitado no servidor e restrito a loopback/Host/Origin locais. Hash scrypt, definição/alteração de senha no site, invalidação de sessões por geração, inicialização única e persistente. Sessões HttpOnly/SameSite, CSRF e limitação de tentativas.
- Perfis de administrador, gerente, recepção, professor e estagiário. Dados financeiros e de escala têm barreiras próprias na API. Admin/gerente não criam reservas particulares ou Platinum contornando os perfis operacionais.
- Cadastro de alunos, internos e externos; CREF/CRN correspondente; tutor obrigatório na criação de estagiário; CPF, nome completo e telefone normalizados; unicidade por identidade. Contas individuais criadas por admin, sem login para externo/aluno.
- Durações de 20/30/40/50/60 minutos, preços em centavos, limite diário, janelas contínuas, compartilhamento/exclusividade e configuração avançada do funcionamento e feriados. Configurações versionadas, vigência e termos capturados. Bloqueio de mudanças incompatíveis com reservas.
- Perfil Panobianco: 20 inícios diários de 30 minutos para alunos, sexta de marcação para próxima segunda–quinta, inclusive sexta feriado; sem avaliação de alunos no feriado; competência do mês do atendimento e trava por CPF que sobrevive ao cancelamento/falta.
- Particulares de 60 minutos; interno gratuito e fora da jornada; externo R$40, fim de semana por padrão, liberação global de dias úteis por admin. Duração cabe integralmente no funcionamento. Consulta de disponibilidade fornece motivo do bloqueio.
- Consentimento externo com checkbox desmarcado e captura de operador, instante e versão; termos alterados entre a tela e a confirmação exigem novo aceite. Reserva temporária, expiração, conferência manual com valor exato/referência única e revalidação após expiração.
- Cancelamento externo calcula retenção/reembolso pelo pagamento e política originais uma única vez. Reembolso fica pendente até registro da devolução efetiva. Causa da academia não aplica retenção. Não movimenta dinheiro.
- Penalidade interna de 48h por identidade profissional, verificada na criação por qualquer operador. Jobs idempotentes de expiração e falta. Falta por uso profissional só é ativada se o administrador confirmar explicitamente critério e prazo; o padrão mantém isso pendente.
- Presença do aluno até início+5min, falta automática posterior, WhatsApp manual independente, treino por responsável/tutor, correção de atraso exclusiva da recepção com motivo ativo e registro da presença efetiva.
- Bloqueios de sala ou profissional, motivo obrigatório, professor limitado a si mesmo, remoção conforme origem. Atendimento afetado exige decisão individual. Manter divide o bloqueio; realocar move a mesma reserva e ocupa o benefício do mês de destino sem liberar a origem. Concorrência falha atomicamente.
- Jornadas com vigência e contrato, propostas de escalas por ciclo de 84 dias, sábado+domingo, sete dias, 11h de descanso, folga pré-feriado, carga semanal, vínculo, função, horário, cobertura e conflitos com reservas. Ajuste de sexta do noturno para abrir sábado; feriado domingo não duplica composição.
- Rascunhos editáveis em JSON, alocação manual preservada, versões imutáveis após publicação e controle de concorrência. Pendência impede publicação. Equipe vê somente mês vigente; motor usa ciclo e fronteiras. Geração de outro ciclo usa data de referência sem reiniciar âncora em janeiro.
- Cessão de plantão em Permutas: solicitante → aceite do colega → validação do admin → nova versão; invalida escala desatualizada e recalcula ajustes. Sem orientação automática de ponto em dia distinto.
- Auditoria persistente, notificações internas para operação, métricas simples, exportação JSON por unidade, backup online e restauração verificada com invalidação das sessões recuperadas.

## Funcionalidades parciais ou pendentes

Esta entrega **não conclui todos os 67 critérios comerciais**. Os testes automatizados cobrem cenários representativos e críticos; não equivalem a homologação integral da especificação.

| Área | Limite desta versão |
|---|---|
| Sites / acesso remoto | Sem Site remoto ou preview acessível ao usuário. Helpers/Vinext e navegador do skill indisponíveis; backend local Python requer adaptação para runtime e banco hospedados do Sites. Sem implantação remota protegida ou produção. |
| Segurança de produção | Recuperação segura de senha, MFA/reforço de admin, TLS, gestão de segredos hospedados, monitoramento externo e revisão independente pendentes. Servidor bloqueia ambiente diferente de local. |
| Produto multiacademia | Isolamento e organizações demonstrativas prontos; cadastro comercial de organizações, personalização completa de marca, administração da plataforma e suporte com autorização/auditoria próprios pendentes. Não existe conta global de plataforma disfarçada de admin. |
| Administração da equipe | Criar pessoas, contas e jornadas está pronto; editar/inativar profissionais, transferir unidade, trocar tutor com impacto e reconciliar correção de CPF não estão expostos. A ausência de endpoint de edição evita alterações órfãs. Férias, afastamentos, elegibilidade detalhada e vigências de vínculo ainda precisam de cadastros próprios. |
| Oferta avançada | Janelas compartilhadas/exclusivas e limite disponíveis; prévia completa de calendário com avaliadores por janela, exceções de oferta por data e distribuição editável de todos os inícios ainda pendentes. Distribuição inicial usa primeiros inícios sequenciais das janelas. Oferta semanal bruta não desconta feriados nem indisponibilidade dos profissionais. |
| Feriados / externos | Configuração por JSON e liberação global de dias úteis prontas; liberação/bloqueio de externos por faixa/data/semana, fechamento emergencial e editor visual de calendário pendentes. Após escala publicada, mudanças de calendário/âncora são recusadas até existir fluxo completo de revisão de impacto. |
| Tutoria de reservas | Integridade do cadastro e checagem de conflitos prontas. Aprovação autenticada pelo tutor existe na API após configurar política; fluxo completo de solicitação/aceite/supervisão e substitutos por turno não está pronto na interface. Reservas de estagiário ficam desabilitadas por padrão, com motivo explícito. Consultar escala como estagiário funciona. |
| Pix e devoluções | Modal, conciliação, retenção e registro manual prontos. Upload/exibição de QR externo e comprovantes, fluxo dedicado de pagamento recebido sem vaga após expiração, estados de falha e revisão de conciliação ainda parciais. Nenhum QR bancário real foi cadastrado. Não exibe devolução como concluída antes do registro. |
| Estados operacionais | Presença/contato/treino/uso separados e auditados. Encerramento formal em uso/concluída, revisão administrativa de penalidade, restituição motivada de benefício e correções gerais ainda parciais. Casos não suportados são recusados ou mantidos pendentes. |
| Escalas | Motor validado e geração inicial funcional. Modelos de vagas estão no módulo de configuração do motor, ainda sem editor no site; critérios contratuais têm carga semanal, mas não cobrem banco de horas/feriados regionalizados. Editor visual de vagas, comparação de versões, revisão de publicação por admin sem permuta, travamento durante regeneração e equidade histórica detalhada de domingos são pendentes. Gerador guloso pode deixar vagas descobertas; não garante solução ótima. |
| Permutas | Cessão de um plantão está pronta. Troca recíproca de dois plantões em um único pedido e exportação especializada de divergências de ponto pendentes. Dados constam na exportação JSON. |
| Relatórios / tarefas | Métricas e exportação geral prontas. Relatórios analíticos completos de equidade/ocupação, filtros combinados de sala/profissional/status, alertas para toda equipe, lembretes agendados, retenção automática e cópias remotas pendentes. |
| Teste visual | TypeScript e sintaxe JS verificados; HTTP e regras testados. Sem inspeção de navegador, captura de tela ou validação visual/mobile nesta execução. |

## Decisões de negócio que continuam pendentes

O padrão de demonstração não presume aprovação real destas decisões:

- Data-âncora: novembro de 2026 é exemplo e exige confirmação no site antes da publicação de escala.
- Prazo de confirmação de uso profissional e critério de falta: `null`/desabilitado por padrão, sem assumir duas horas.
- Supervisão, aprovação e penalidade do estágio: desabilitadas até confirmação administrativa e conclusão do fluxo de interface.
- Política de ponto e orientação de RH/Myaghora: sem integração ou procedimento automático.
- Feriados reais, equipe real, jornadas, planos, catálogo de justificativas, QR/recebedor, prazo de devolução e textos comerciais precisam de validação pela academia.

## Arquitetura e escolha local

SQLite com serialização de gravações foi escolhido para teste local sem serviços externos ou credenciais. O frontend é tipado e o backend usa apenas biblioteca padrão Python. Isso difere do starter Vinext recomendado pelo Sites porque os helpers e templates não estavam presentes no ambiente. Não há manifest de hospedagem nem identidade de Site inventada. Migração para ambiente compartilhado requer uma nova etapa; não basta expor este servidor na internet.
