# Manual por perfil

**Administrador:** configura a unidade ativa, cria sala, pessoas e contas, versiona jornadas e políticas, mantém motivos de atraso, gera/revisa/publica escalas válidas e consulta auditoria/exportação. Minha conta define a senha e encerra o modo inicial. Não usa o perfil administrativo para marcar Platinum/particulares nem para reverter falta automática exclusiva da recepção. Pode efetivar realocação por imprevisto.

**Gerência:** acompanha agenda, pessoas, financeiro, escalas publicadas, permutas e exportação da própria unidade; não publica escalas ou altera regras. Mantém o catálogo de motivos pela API administrativa autorizada (o editor está na tela do admin; interface de gerência para isso é pendente).

**Recepção:** cadastra alunos e Personal/Nutricionista externos, marca alunos e externos, registra concordância, presença/contato, cobrança/devolução manual, bloqueios e realocações. Pode registrar reserva interna respeitando penalidade/jornada. Somente este perfil justifica falta automática de aluno com motivo ativo. Não acessa escala, suas jornadas ou exportação de escalas.

**Professor:** consulta agenda diária completa, seus impedimentos, escala publicada do mês vigente e permutas. Reserva particular para si fora da jornada; altera contato/presença/treino apenas dos atendimentos sob responsabilidade, inclusive como tutor. Bloqueia somente sua própria disponibilidade. O backend valida qualquer chamada direta.

**Estagiário:** tem conta individual vinculada a tutor e CPF próprios, consulta agenda completa e escala do mês e solicita permutas da mesma função. Não valida treino autonomamente nem bloqueia toda a sala. Solicitação/aprovação de reserva supervisionada está parcial e desabilitada no padrão; não apresentar isso como reserva confirmada.

**Externo / aluno:** somente cadastro operacional, sem login, convite ou acesso à agenda. Pix é conduzido pela recepção e conferido manualmente. Qualquer confirmação durante os testes representa dado fictício e não transferência real.

Em falha de conexão, a interface mostra erro; não há confirmação offline. Atualização de agenda ocorre por consulta ao servidor a cada 15 segundos e após ações. Se uma operação concorrente ocupar o recurso, o servidor recusa a segunda. Recarregue a agenda e escolha outro horário.
