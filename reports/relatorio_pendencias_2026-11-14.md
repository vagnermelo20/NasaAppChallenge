# Relatório de requisitos e pendências — EMBER

**Data:** 14/11/2026, horário de Fortaleza.  
**Versão revisada:** `f03459c` — entrega científica da pessoa A, posterior à interface `56da6d3`.  
**Base da revisão:** especificações, tarefas, código, Parquet entregue, metodologia e métricas do repositório.

Este relatório distingue requisito não atingido, validação ainda não demonstrada e melhoria opcional. Não altera os dados nem substitui uma revisão científica completa. Os critérios numéricos citados são os definidos pelo próprio grupo em `specs/spec.md`; não devem ser apresentados como uma regra universal da NASA.

## 1. O que ainda não foi atingido ou comprovado

| Prioridade | Item | Situação comprovada | Próxima ação | Responsável |
|---|---|---|---|---|
| Alta | **A2 — acerto do mês de pico por célula** | Na avaliação oficial disponível da versão 1, o acerto foi **72,7%**, abaixo dos **80%** exigidos. Faltam **7,3 pontos percentuais**. A correlação de **0,951** supera o mínimo de 0,85, mas isso não basta para passar nos dois critérios. | Recalcular as métricas por célula com o método final. Se continuar abaixo da meta, registrar a limitação e discutir explicitamente o escopo; não trocar a escala ou reduzir a meta sem acordo. | A, com decisão do grupo |
| Alta | **A14 / R6 — validação consolidada do método final** | O próprio `metrics.json` informa que `loyo_2012_2021` ainda descreve a versão 1. O método final está em `prova_harmonizacao`, com refinamento local e combinação diferente dos satélites. | Rodar novamente o notebook 05 com o método final e atualizar a avaliação oficial A2, as figuras e a descrição do método. | A |
| Alta | **R5b — dados de 2026 / cobertura até o presente** | A base termina em **dezembro de 2025**. Há **zero registros de 2026**. O notebook de 2026 existe, mas a tarefa A9 continua pendente da MAP_KEY. | Obter a chave FIRMS, baixar e processar o período disponível de 2026 e aplicar as regras de qualidade. Até isso ocorrer, informar claramente o corte em 2025. | A |
| Alta | **A4 / J1 — publicação** | O projeto está no GitHub e roda localmente, mas não há link público do app registrado. A publicação havia sido adiada por decisão do grupo até a chegada dos dados reais. | Depois da revisão científica e da integração, publicar e testar o link público nas três regiões. | A + B |
| Média | **A4 / J3 — vídeo de 30 s e apresentação** | Não há conclusão registrada dessa entrega no controle de tarefas. Esta revisão não comprova a existência de vídeo final fora do repositório. | Gravar a demonstração com dados reais e números compatíveis com a validação final. | A + B |
| Média | **B10 — aceitação visual e acessibilidade** | Há implementação e testes automáticos, mas a conferência manual no Chrome/celular, do desenho Leaflet e da imagem PNG continua sem aceite registrado. | Executar `app/VERIFY.md` no navegador real, incluindo largura estreita, região vazia e exportação PNG. | B / usuário |
| Média | **J2 e J4 — documentação final e submissão** | README e roteiro estão preparados, mas faltam atualização do estado da entrega, créditos finais, URL pública e conclusão registrada da submissão. | Atualizar a documentação após a integração e conferir o envio no portal do evento. | A + B |

**Leitura correta do A2:** a versão 1 não atingiu a meta por célula. Para o método final, o atendimento desse mesmo critério ainda não está demonstrado. Não é correto atribuir automaticamente os 72,7% ao método final, nem declarar que ele passou com base em uma métrica de outra escala.

## 2. Ajustes de integração encontrados

### 2.1 O Fire map ainda lê a grade anterior

O mapa observado usa `data/processed/grid_monthly.parquet`. A série científica final usa o processamento novo, com `grid_sat.parquet` e a máscara revisada. Portanto, o mapa e o calendário podem mostrar números diferentes mesmo para o mesmo sensor e mês.

**Exemplo conferido: VIIRS S-NPP, Brasil, setembro de 2024.**

| Fonte | Contagem |
|---|---:|
| Fire map / grade antiga | 602.522 |
| Grade nova, somando S-NPP | 598.825 |
| Calendário real, `fonte = viirs` | 598.825 |
| Diferença entre grade antiga e série final | **3.697** |

A diferença é de aproximadamente **0,62%** em relação à série final. Ela evidencia preparação diferente das bases, não um erro comprovado na soma da interface.

**Ação:** adaptar a camada observada para agregar `n` por satélite a partir da grade nova, ou manter a grade antiga com identificação explícita de que os filtros diferem. A preferência para uma apresentação consistente é usar a mesma preparação científica. Não é necessário alterar o contrato de `harmonized.parquet`.

### 2.2 Textos do app e do README ficaram desatualizados

- O README ainda descreve o estado geral como desenvolvimento com mock e dados finais pendentes.
- A aba About contém texto fixo dizendo que o calendário é mock até os dados chegarem, mesmo quando o arquivo real já está selecionado.
- Há mensagens genéricas de calibração/validação pendente que precisam distinguir arquivos recebidos de critérios científicos ainda não aprovados.

**Ação:** fazer os textos refletirem a fonte efetivamente carregada e manter visível a pendência real do A2/A14. A chegada de dados reais não significa aprovação científica automática.

### 2.3 A aba Methodology ainda não destaca toda a prova final entregue

O texto novo é carregado e as métricas são exibidas em JSON. Porém, a seleção de figuras ainda não inclui `prova_antes_depois.png` e `prova_pantanal.png`, solicitadas no handoff. As seções de métricas da versão anterior e do método final aparecem juntas, sem um resumo específico da avaliação final.

**Ação:** destacar `prova_harmonizacao`, identificar as métricas antigas como versão 1 e mostrar as figuras principais do método final. A funcionalidade básica R11 existe; falta atualizar a apresentação para a entrega científica nova.

## 3. Inconsistências documentais a resolver

1. **Cobertura de 2026:** a metodologia menciona dados de 2026 via API e uma série até o presente, mas o arquivo recebido só vai até 2025. Esses trechos precisam indicar que 2026 está planejado, enquanto o download não for concluído.
2. **Sinal da faixa de incerteza para até 20 focos MODIS:** metodologia e handoff mencionam **−6% a +229%**; a tabela em `metrics.json` contém **+6% a +229%**. A pessoa A deve confirmar o sinal correto antes de o intervalo ser incorporado à interface.
3. **Especificação da máscara:** R2 ainda descreve uma máscara em células de 0,25° com `type=2` em qualquer ano. A entrega implementa uma máscara de 0,02°, tipos 1/2/3 em pelo menos dois anos. Isso é uma divergência documental; não prova que o método novo seja incorreto. O requisito e a justificativa precisam ser alinhados formalmente.
4. **Método e métricas:** o cabeçalho descritivo do JSON ainda apresenta a média simples Terra/Aqua, enquanto o método final usa combinação pelo inverso da variância e refinamento local. A nota no arquivo reconhece essa diferença, mas a descrição principal deve ser consolidada.

## 4. Limitações e melhorias opcionais — não são falhas automáticas do escopo

- A faixa de incerteza de 90% foi proposta no handoff, mas ainda não está implementada no app nem incluída como colunas na base final. É uma melhoria opcional; seu uso depende de resolver a inconsistência do sinal e definir como calcular o intervalo para a região consultada.
- O aviso específico sobre menor confiabilidade de regiões pequenas antes de 2012 pode ser melhorado na interface. A metodologia recomenda regiões de aproximadamente 1° ou maiores.
- A marcação de meses incompletos usa dias sem registros em todo o Brasil como indicador. É uma regra operacional documentada; não constitui, sozinha, uma auditoria de todas as oportunidades de observação ou de cobertura por nuvens.
- “92% dentro de ±20% por ano em regiões de 2°” é uma evidência útil, mas não equivale a “80% de acerto do mês de pico por célula de 0,25°”. Não misturar essas afirmações no pitch.
- A observação sobre um suposto teto de concordância de sensores deve ser apresentada como resultado do estudo descrito pela equipe, não como uma prova universal de impossibilidade física.

## 5. O que foi conferido e não deve continuar listado como ausente

**A pessoa A entregou os quatro arquivos principais:** `harmonized.parquet`, `metodologia.md`, `metrics.json` e `harmonizado_anual.png`, além das bases auxiliares e das figuras de prova.

| Verificação | Resultado |
|---|---|
| Seleção automática da base pelo app | `harmonized.parquet`, sem escolher o mock |
| Quantidade de registros | **1.212.739** |
| Células distintas | **11.127** |
| Cobertura temporal | **2001–2025; 300 meses** |
| Meses com flag de incompletude | **15** |
| Duplicatas de célula × mês | **0** |
| Desalinhamento da grade de 0,25° | **0** |
| Fonte incompatível com o período pré/pós-2012 | **0** |
| Comparação da série VIIRS final com a grade nova S-NPP | **0 diferenças por célula/mês** |
| Formato e valores básicos | Aceitos pelo validador do app |
| Testes automáticos executados com a base real presente | **19 aprovados** |

**Consultas regionais da base real (caches regionais inicialmente vazios no processo de revisão):**

| Região de teste | Meses | Tempo observado | Soma por SQL independente | CSV |
|---|---:|---:|---|---|
| Pantanal — retângulo −58/−55° lon, −20/−16° lat | 300 | **0,121 s** | Coincide | Coincide |
| Matopiba — retângulo −48/−44° lon, −13/−7° lat | 300 | **0,060 s** | Coincide | Coincide |
| Acre — retângulo −74/−66° lon, −12/−7° lat | 300 | **0,058 s** | Coincide | Coincide |

Esses tempos atendem ao limite de 3 s para as consultas medidas localmente. Não são uma garantia do tempo de renderização do mapa no navegador nem do desempenho de uma futura hospedagem.

O verificador de artefatos retornou **`ready_for_review`**, sem arquivos faltantes ou inválidos. Esse estado significa disponibilidade para revisão; não significa que A2, a aceitação visual ou a publicação foram aprovados.

## 6. Ordem recomendada para concluir

1. **A:** recalcular a validação oficial do método final e resolver a situação do A2 por célula.
2. **A + B:** alinhar descrições, cobertura temporal, sinal da incerteza e nomes/versões das métricas.
3. **B:** integrar a grade nova ao Fire map e atualizar About, README e Methodology para a fonte real.
4. **B / usuário:** concluir a conferência visual no Chrome/celular e da exportação PNG.
5. **A:** concluir 2026, se mantido o requisito R5b; caso contrário, registrar e aprovar explicitamente o corte temporal.
6. **Grupo:** publicar, testar o link público, finalizar vídeo/créditos e registrar a submissão.

## Evidências locais

- [Requisitos e critérios](../specs/spec.md)
- [Controle de tarefas](../specs/tasks.md)
- [Handoff da pessoa A](../specs/handoff_A_para_B.md)
- [Métricas e nota de versão](metrics.json)
- [Metodologia](../docs/metodologia.md)
- [Código da aplicação](../app/app.py)
- [Roteiro de verificação visual](../app/VERIFY.md)

As verificações desta revisão foram somente de leitura sobre as bases. Não foram recalculados os modelos científicos nem alterados os arquivos entregues pela pessoa A.
