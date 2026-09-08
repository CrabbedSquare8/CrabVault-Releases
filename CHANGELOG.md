# CrabVault — Changelog

## v0.45.0 — 04/09/2026

- Publishes an audited source snapshot in the public `CrabVault-Releases` repository while keeping the private development repository and its history private.
- Adds the CrabVault Source-Available Non-Commercial License and an English public source README.
- Shows the total number of official installer asset downloads reported by GitHub; the value is cached and is explicitly not a count of unique users.
- Corrects the internal application version and keeps releases and verified updates on `CrabbedSquare8/CrabVault-Releases`.

## v0.44.11 — 04/09/2026

- Permite mover a janela puxando qualquer área livre da barra superior customizada, mantendo minimizar, maximizar e fechar como controles clicáveis.
- Dimensiona e centraliza a janela inicial de acordo com a área útil do monitor, usando margens em telas menores em vez de abrir ocupando toda a tela.
- Finaliza em inglês os termos de uso, a política de privacidade e os avisos de terceiros distribuídos; esclarece que a verificação SHA-256 manual é opcional, embora permaneça obrigatória e automática no atualizador interno.

## v0.44.10 — 04/09/2026

- Remove dos cards o controle visual de prioridade (`− número +`), pois ele não controla a ordem real de carregamento usada pelo jogo.
- Retira prioridade dos detalhes e das explicações do tutorial/perfis; conflitos passam a orientar diretamente a escolha do conteúdo a manter ou a desativação do concorrente.
- Mantém valores antigos apenas na persistência interna para compatibilidade com catálogos, perfis e históricos existentes.
- Build protegida, instalador e pacote portátil foram gerados e aprovados em teste manual, incluindo persistência, classificação, navegação responsiva e previews BK2.

## v0.44.9 — 03/09/2026

- Aquece e mantém em memória os cards preparados na primeira carga; buscas, filtros, ordenações e a saída de Backgrounds passam a mover/reutilizar nós existentes em vez de recriar sua estrutura e eventos.
- Reconstrói um card apenas quando seu conteúdo realmente muda e limpa o cache após reloads ou mutações da biblioteca.

## v0.44.8 — 03/09/2026

- Renderiza bibliotecas grandes em lotes de 18 cards por frame, liberando imediatamente a interface para sair de Backgrounds, focar a busca e trocar filtros.
- Cancela automaticamente os lotes antigos quando uma pesquisa ou filtro inicia outra renderização, evitando trabalho inútil e resultados misturados.

## v0.44.7 — 03/09/2026

- Mantém no frontend os detalhes já transferidos pela ponte do WebView, evitando reenviar e reconstruir quase 1 MB de metadados e centenas de cinematics a cada reabertura do mesmo mod.
- Invalida essa cópia ao recarregar a biblioteca, atualizar um mod ou aplicar uma alteração local, preservando dados atuais sem sacrificar a reabertura imediata.

## v0.44.6 — 03/09/2026

- Reutiliza em memória os metadados completos dos detalhes enquanto catálogo e configurações permanecem iguais, eliminando a espera repetida ao fechar e reabrir um Background grande.
- Invalida o cache automaticamente após mudanças persistentes e entrega cópias isoladas para impedir que alterações da interface contaminem reaberturas futuras.

## v0.44.5 — 03/09/2026

- Restaura as previews de vídeo BK2 com o Bink Player 2026.06 oficial e inalterado, incorporado ao executável protegido e preferido antes de instalações no `PATH`.
- Valida o SHA-256 do player antes da build e inclui no pacote o crédito e as condições de redistribuição não comercial da RAD/Epic.

## v0.44.4 — 03/09/2026

- Torna a navegação rápida dos cards responsiva: cada tecla atualiza apenas o destaque, a pintura é agrupada por frame e a rolagem não acumula animações suaves.
- Adiciona WASD à navegação principal, com o mesmo comportamento das setas e sem capturar letras enquanto o usuário edita campos.

## v0.44.3 — 03/09/2026

- Faz o scan aplicar também personagem e skin detectados nos assets do componente visual principal, sem reler o pacote e sem substituir correções manuais.
- Componentes Physics continuam fora da decisão de identidade para não atribuir incorretamente a skin Default ao mod principal.

## v0.44.2 — 03/09/2026

- Faz o scan de `~mods` concluir a classificação profunda dos pacotes externos antes de atualizar os cards, reutilizando o cache nos scans seguintes.
- Exibe durante a primeira varredura um aviso bilíngue de que a identificação dos tipos pode demorar em bibliotecas grandes.

## v0.44.1 — 03/09/2026

- Inclui corretamente no executável onefile todos os binários auxiliares, que o Nuitka não considera arquivos de dados: UAssetTool, HandBrakeCLI, 7-Zip, vgmstream, runtime .NET e extrator 3D.
- Restaura a leitura interna dos assets durante o scan, evitando que mods Mesh sejam classificados como `Unknown` apenas porque o UAssetTool estava ausente da build.
- Preserva configurações e estado do tutorial ao lado do executável externo, em vez da pasta temporária do onefile.

## v0.44.0 — 03/09/2026

- Substitui a distribuição técnica visível por um executável único compilado com Nuitka, incorporando backend, interface e ferramentas usadas em tempo de execução.
- A instalação passa a expor somente `CrabVault.exe`, dados criados pelo usuário e a pasta `Licenses` com os avisos obrigatórios; atualizações removem a antiga pasta `Aplicativo` sem tocar em mods, mídias ou configurações.
- Mantém auditoria de privacidade, manifesto SHA-256, fontes correspondentes de terceiros, ícone e atualizador verificado.
- Corrige o build quando o caminho do Python contém caracteres acentuados, usando os binários e a pequena pasta de DLLs em caminho ASCII sem duplicar as pastas grandes da instalação.
- Mantém configurações, catálogo, biblioteca e estado do tutorial ao lado do executável externo; a execução onefile não grava mais esses dados na pasta temporária descartada ao fechar.

## v0.43.4 — 02/09/2026

- Completa a tradução inglesa das Configurações, incluindo textos divididos por links e trechos de código, além dos estados dinâmicos do suporte ao visualizador 3D.

## v0.43.3 — 02/09/2026

- Substitui a confirmação branca nativa do WebView no fluxo de atualização por um diálogo próprio do CrabVault, bilíngue e acessível, que destaca a validação SHA-256, a preservação dos dados e o reinício necessário.

## v0.43.2 — 02/09/2026

- Atualização de teste para validar, a partir da v0.43.1 instalada, a consulta, o download verificado e a execução do instalador publicado em `CrabVault-Releases`.

## v0.43.1 — 02/09/2026

- Direciona a consulta e os downloads do atualizador para o repositório público dedicado `CrabbedSquare8/CrabVault-Releases`, mantendo o código-fonte principal privado.
- A validação continua aceitando somente URLs, nomes de instalador e arquivos SHA-256 pertencentes ao repositório oficial de releases.

## v0.43.0 — 02/09/2026

- Organiza a distribuição em `CrabVault.exe`, `mods_storage` e `Aplicativo`, que concentra frontend, backend, ferramentas, runtimes, DLLs, documentação e manifesto.
- O instalador acrescenta a pasta `CrabVault` ao destino escolhido sem duplicá-la quando ela já faz parte do caminho.
- Executável e atalhos passam a declarar explicitamente a logo do CrabVault como ícone.

## v0.42.0 — 02/09/2026

- Adiciona verificação manual de atualizações nas Configurações usando a release estável mais recente de `CrabbedSquare8/CrabVault`.
- Aceita apenas os artefatos oficiais esperados, bloqueia downgrade e valida o instalador pelo SHA-256 publicado antes de executá-lo.
- Atualiza a mesma pasta preservando configurações, catálogo, mods e mídias. Nenhum token do GitHub é armazenado; repositórios privados exibem a limitação de acesso anônimo.

## v0.41.0 — 02/09/2026

- A distribuição deixa de incorporar os 798 MB do WebView2 Fixed Version e passa a usar o WebView2 Evergreen compartilhado e atualizado pela Microsoft.
- Antes de abrir a interface, o CrabVault verifica a instalação disponível. Se ela estiver ausente ou abaixo da versão mínima testada, uma janela nativa bilíngue explica a dependência e pede autorização antes de baixar o bootstrapper oficial, validar sua assinatura Microsoft e instalá-lo.

## v0.40.3 — 02/09/2026

- O instalador sempre exibe a etapa de escolha da pasta de destino, inclusive ao reinstalar ou atualizar uma instalação já reconhecida pelo Windows.

## v0.40.2 — 02/09/2026

- O executável Windows agora incorpora um ícone multirresolução com a logo vermelha do caranguejo. Os atalhos do menu Iniciar e da Área de Trabalho criados pelo instalador passam a exibir a identidade do CrabVault em vez do ícone genérico.
- O gerador de build habilita `vm.SourceTextModule` ao executar os testes no Node.js 18, evitando interromper uma release válida no teste dos controles do visualizador.

## v0.40.1 — 02/09/2026

- Corrigida a mensagem de falha do visualizador 3D em inglês quando o caminho configurado não leva à pasta `Paks`; título, contexto e detalhe agora aparecem integralmente em inglês.
- A instalação v0.40.0 foi validada fora do checkout: interface, marca, runtime, visualizador e modelo 3D abriram normalmente com o caminho correto do jogo.
- Adicionado `Gerar Build.bat`: um gerador de release por duplo clique que obtém a versão da interface, executa as suítes, cria e audita bundle, ZIP, instalador, hashes, metadados e fontes correspondentes sem sobrescrever artefatos anteriores.

## v0.40.0 — 02/09/2026

- A Oodle 2.9.10 deixa de entrar no executável/ZIP. No primeiro preparo do visualizador 3D, o CrabVault baixa a DLL diretamente do commit fixado do WorkingRobot/OodleUE, valida HTTPS, limite de tamanho, PE x64 e SHA-256 e só então publica o arquivo no cache privado.
- README, Configurações, privacidade e avisos mencionam o WorkingRobot/OodleUE, a propriedade Epic/RAD e a EULA da Unreal Engine. Depois do preparo, o visualizador continua funcionando offline com a cópia validada.
- Validação direcionada: instalação nova, cache offline, migração da 2.9.16, rejeição de download adulterado, visualizador e fronteira do pacote passaram; a DLL não é copiada pela especificação de release. O download real retornou 637.952 bytes e o SHA-256 esperado.

## v0.39.2 — 02/09/2026

- Criado o portão público de conformidade com inventário versionado e hashes dos binários principais, política de privacidade, rascunho de termos proprietários e resumo explícito dos bloqueios restantes.
- O pacote de fontes correspondentes agora inclui o patch e a receita reproduzível do UAssetTool sanitizado. As 42 dependências NuGet do extrator 3D têm licença identificada e os textos antes ausentes foram incorporados.
- A redistribuição pública da Oodle 2.9.10 fica bloqueada até existir autorização aplicável documentada; origem pública, hash e pasta `redist` não são tratados como licença.
- Validação: suíte Python com 366 casos concluída sem falhas (um ignorado), bootstrap do runtime 3D aprovado e os quatorze arquivos JavaScript passaram. Nenhum bundle executável foi gerado.

## v0.39.1 — 02/09/2026

- A barra de título passa a exibir somente o ícone do caranguejo. O cabeçalho principal recebe um caranguejo maior seguido do nome **CrabVault**, substituindo o texto antigo “Marvel Manager”.

## v0.39.0 — 02/09/2026

- O aplicativo passa a se chamar **CrabVault** na interface, janela, executável, pasta portátil, ZIP, instalador, atalhos, backups e mensagens ao usuário.
- Os nomes internos das pastas de dados existentes foram preservados para manter compatibilidade com bibliotecas e configurações já criadas.

## v0.38.4 — 02/09/2026

- Removidos os fallbacks particulares `D:\Winrar`/`D:\Downloads` do importador de compactados e da otimização de vídeo. A distribuição continua usando primeiro 7-Zip e HandBrakeCLI incluídos e conserva somente a descoberta genérica por `Program Files`/`PATH` no código-fonte.
- O auditor do pacote agora examina também o conteúdo binário e rejeita caminhos absolutos do checkout ou do perfil que produziu a build.
- Recompilados UAssetTool e extrator 3D sem símbolos/caminhos de depuração da máquina de desenvolvimento, preservando versão e comportamento do UAssetTool em testes comparativos.

## v0.38.3 — 02/09/2026

- Substituída a Oodle comunitária 2.9.16 baixada no primeiro uso pela DLL 2.9.10 da pasta `win/redist`, incluída e verificada pelo Manager. A origem foi fixada em commit imutável e o SHA-256 é conferido antes de ativar o suporte.
- Caches da v0.31.0–v0.38.2 são migrados localmente para a 2.9.10 sem baixar novamente o mapping ou perder o suporte anterior em caso de falha.
- Compatibilidade validada no extrator independente com o componente Lopunny: conversão PNG e caminho GPU leram 16 pacotes, geraram os dois modelos e terminaram sem falhas. Validação: 361 testes Python executados, 360 aprovados e um ignorado; os quatorze arquivos JavaScript passaram. Nenhum build portátil foi gerado.

## v0.38.2 — 01/09/2026

- Unificadas as entradas externas **Iron Fist** e **Iron Fist (Lin Lie)** em um único personagem. Todas as skins de Lin Lie agora aparecem sob **Iron Fist**, sem criar um segundo filtro na barra lateral.
- A normalização é aplicada também ao cache já baixado, portanto não exige apagar o catálogo nem baixar novamente. Validação: 360 testes Python executados, 359 aprovados e um ignorado. Nenhum build portátil foi gerado.

## v0.38.1 — 01/09/2026

- Removida a seção **Pastas** da barra lateral, junto do filtro em árvore e do botão de criação exibidos nela, deixando a coluna focada em personagens e tipos.
- A organização interna por pastas foi preservada: destinos de instalação, movimentação de mods e caminhos já cadastrados continuam funcionando normalmente.
- O tutorial foi ajustado para não apresentar pastas como filtro disponível. A sintaxe do frontend e os quatorze arquivos de teste JavaScript passaram; nenhum build portátil foi gerado.

## v0.38.0 — 01/09/2026

- Integrada a base pública `donutman07/MarvelRivalsCharacterIDs`, a mesma fonte de IDs de personagens e skins usada pelo Repak X. O Manager consulta a tabela em segundo plano no máximo uma vez por dia e também oferece atualização manual nas Configurações.
- O catálogo incluído permanece como fallback totalmente offline. Downloads são limitados, validados e publicados atomicamente em um cache separado; falhas ou dados truncados preservam a última cópia válida.
- Novos IDs entram em uso na sessão atual sem reiniciar nem reanalisar mods. Entradas locais ausentes na fonte externa são preservadas, enquanto nomes atualizados substituem somente o mesmo ID. Os ícones continuam vindo dos recursos e do catálogo Rivalskins que o Manager já utilizava.
- A seção bilíngue de catálogo mostra quantidade, última verificação, falha com fallback e atribui a fonte original. Validação: 359 testes Python executados, 358 aprovados e um ignorado; os quatorze arquivos JavaScript passaram. Nenhum build portátil foi gerado.

## v0.37.1 — 01/09/2026

- Adicionado o pipeline do instalador tradicional para Windows x64. Ele usa o mesmo bundle auditado do portátil, permite escolher a pasta, oferece atalhos opcionais e registra a desinstalação sem empacotar catálogo, configurações ou biblioteca do usuário.
- Gerados localmente o ZIP portátil e o instalador v0.37.1. O bundle limpo contém 1.413 arquivos; a instalação isolada conferiu o hash de todos eles e a desinstalação removeu tanto a pasta temporária quanto a entrada do Registro. Os executáveis ainda não possuem assinatura de código.
- Corrigidas as marcações das demonstrações: a seleção de pacotes agora enquadra o ZIP e o trio PAK/UCAS/UTOC; o menu de tags aparece inteiro; identidade, galeria e tags ficam dentro da área explicada; e o rótulo da lista de componentes foi encurtado e movido para fora do conteúdo.
- O capítulo Scan foi reduzido a uma única etapa. Ela explica diretamente que **Buscar mods instalados** transforma os pacotes já colocados em `~mods` nos cards correspondentes, agrupando o trio do mesmo pacote.
- Configurações ganhou três explicações ilustradas para pasta/suporte 3D/exibição/idioma, preservação de origens/bloqueio/manutenção e backups/aparência. Capturas verticais usam um layout lateral para manter imagem, explicação e navegação visíveis ao mesmo tempo.
- O tour passa a ter dez imagens demonstrativas distribuídas com o aplicativo e dezesseis etapas bilíngues em cinco capítulos.
- Validação: 351 testes Python executados, 350 aprovados e um ignorado pela restrição de symlink do Windows; os quatorze arquivos JavaScript passaram. As telas apontadas e as novas Configurações foram revisadas visualmente em servidor isolado. Nenhum build portátil foi gerado.

## v0.37.0 — 01/09/2026

- O tour bilíngue foi ampliado de seis para quinze etapas, reunidas em cinco capítulos navegáveis: início, instalação PAK, mod e detalhes, scan e organização. Etapas ligadas à interface continuam usando spotlight; exemplos que precisam existir mesmo numa biblioteca vazia usam capturas demonstrativas incluídas no aplicativo.
- A instalação PAK agora explica a seleção de ZIP/RAR/7z, PAK legado ou trio PAK/UCAS/UTOC, inclusive múltiplos compactados ou pacotes reunidos como componentes do mesmo mod. O fluxo acompanha a revisão do nome e tipos, tags, seleção múltipla de imagens e o card final instalado.
- O capítulo de detalhes apresenta um card de exemplo e divide a página do mod entre identidade/galeria/tags e componentes/variações/complementos, com marcações visuais sobre cada região. O capítulo Scan explica quando indexar arquivos já colocados em `~mods`, o que não é baixado ou extraído e como agrupamento, duplicatas e análise profunda são tratados.
- As nove imagens fornecidas para a demonstração foram reduzidas ao conjunto necessário de sete arquivos e passam a fazer parte do empacotamento portátil. A navegação por capítulos, botões e teclado foi preservada, com painel maior para manter os nomes legíveis.
- Validação: 351 testes Python executados, 350 aprovados e um ignorado pela restrição de symlink do Windows; os quatorze arquivos JavaScript passaram. O tour foi revisado visualmente em servidor isolado com dados temporários. Nenhum build portátil foi gerado.

## v0.36.5 — 01/09/2026

- Alinhado o botão `+` de Tags ao início de seu campo, na mesma posição horizontal do botão azul de Adicionar imagem.

## v0.36.4 — 01/09/2026

- O modal de instalação agora apresenta **Tags** e **Adicionar imagem** em linhas próprias, com rótulos laterais e controles alinhados, preservando o tema visual do Manager.
- A lista e o botão de tags continuam independentes do seletor azul de mídia. Em janelas estreitas, os rótulos passam automaticamente para cima dos controles.
- Português e English exibem os novos rótulos conforme o idioma selecionado. Os quinze testes JavaScript e os onze testes de empacotamento portátil passaram; nenhum executável foi gerado.

## v0.36.3 — 01/09/2026

- O modal de instalação agora ajusta sua altura ao conteúdo nas janelas usuais, mantendo nome, identificação, tags, mídia, explicação e ações visíveis sem rolagem.
- Removido do fluxo visual o rótulo residual de imagem de capa; a seleção de mídia continua disponível pelo botão azul ao lado das tags.
- Em janelas excepcionalmente baixas, a rolagem passa a ser usada apenas no conteúdo central, preservando o cabeçalho e os botões de ação.
- Validação: os quinze arquivos de teste JavaScript passaram, incluindo a nova cobertura responsiva do modal, assim como os onze testes de empacotamento portátil. Nenhum executável foi gerado.

## v0.36.2 — 01/09/2026

- Corrigida a tradução de frases compostas e contadores dinâmicos. Com English selecionado, rótulos como **Folder**, **Mod path**, **Files**, quantidades de arquivos e **Priority** não conservam mais trechos em português.
- Operações interrompidas agora traduzem também títulos e mensagens recebidos do backend, incluindo importação, descarte da preparação, aviso global, revisão, confirmação e resultado da recuperação.
- O tradutor global passa a substituir segmentos conhecidos dentro de uma mensagem, preservando nomes de mods e valores variáveis. Datas exibidas no histórico de componentes usam `en-US` em English e `pt-BR` em Português.
- Validação ampliada para frases híbridas, textos do backend, contadores e alternância de idioma; os quatorze arquivos JavaScript passaram.

## v0.36.1 — 01/09/2026

- Removidas do modal de importação as opções **Ofuscação**, **IoStore híbrido** e **Formato PAK legado**. Elas apenas gravavam marcadores no catálogo e não transformavam os pacotes, portanto não são mais apresentadas como funções disponíveis.
- Removida a árvore lateral **Instalar em / Install to**. A organização automática por personagem, skin e áudio continua sendo calculada internamente, sem exigir uma escolha manual durante a importação.
- O modal foi reduzimensionado para ocupar o espaço liberado. Novas importações passam a registrar `install_options` vazio; registros antigos continuam compatíveis e não são migrados em massa.

## v0.36.0 — 01/09/2026

- O tutorial deixou de cobrir a aplicação com uma apresentação genérica. Agora ele funciona como um tour sobre a interface real, destacando com um spotlight Configurações, PAK, biblioteca de mods, busca/organização, conflitos e segurança/backups.
- O cartão de cada etapa procura espaço ao redor do controle destacado, muda de lado quando não cabe na posição preferida e acompanha redimensionamento ou rolagem. Se a biblioteca estiver vazia, a etapa dos cards usa o cabeçalho real da lista como referência.
- Os seis ícones do tour são clicáveis para saltar diretamente entre assuntos; **Voltar / Próximo** e as setas esquerda/direita continuam a sequência. Títulos, explicações, nomes dos alvos e ações finais possuem textos próprios em Português e English.
- **Rever tutorial** fecha primeiro as Configurações, permitindo que o tour apresente a tela principal em vez de destacar uma interface escondida atrás do modal.
- Validação: 351 testes Python executados, 350 aprovados e um symlink ignorado pela restrição do Windows; os treze arquivos JavaScript passaram. A nova cobertura verifica alvos reais, posicionamento do spotlight, fallback de biblioteca vazia e navegação direta. Nenhum build portátil foi gerado.

## v0.35.2 — 01/09/2026

- A exclusão permanente voltou a exigir duas decisões explícitas dentro do diálogo do Manager. O primeiro clique abre a confirmação final e ainda não altera nenhum arquivo; somente **Sim, apagar tudo** chama a exclusão. A etapa final reforça que registro, pacotes, galeria e compactados não poderão ser recuperados.
- O histórico de atividade agora traduz também o conteúdo gerado pelos registros: mensagens de ativação, desativação, componentes, exclusão permanente e prévia 3D, além dos tempos das importações, estados vazios e datas no formato do idioma escolhido.
- Os detalhes do mod completam a tradução de **Correct**, ausência de tags, contadores de **All / Variations / Add-ons**, origem/data dos componentes, **Diagnostics** e **Relationships**.
- O menu `⋯` traduz seu tooltip e substitui o segundo `⋯` interno por **Manage / Gerenciar**. O diálogo de gerenciamento, o contador de histórico e sua explicação também acompanham o idioma ativo.
- Validação: 351 testes Python executados, 350 aprovados e um symlink ignorado pela restrição do Windows; os doze arquivos JavaScript passaram, incluindo confirmação permanente em duas etapas e o catálogo dinâmico de traduções. Nenhum build portátil foi gerado.

## v0.35.1 — 01/09/2026

- **Remover mod** e **Excluir permanentemente** não usam mais a confirmação branca nativa do WebView, que exibia `127.0.0.1`, misturava textos e adotava os botões do idioma do Windows. As duas ações agora abrem um diálogo interno coerente com o tema do Manager.
- O diálogo usa integralmente Português ou English conforme a preferência do aplicativo, mostra o nome do mod e separa visualmente o que será apagado do que será preservado. A remoção comum informa que mantém galeria e ZIP/RAR/7z; a exclusão permanente destaca que não pode ser desfeita.
- O foco começa em **Cancelar**, Escape e clique no fundo fecham a revisão, Tab permanece dentro do modal e os controles ficam bloqueados durante a operação. Falhas, inclusive o bloqueio pelo jogo aberto, aparecem no próprio diálogo sem remover o card da interface.
- Tooltips dos dois botões e ações equivalentes do menu de contexto também seguem o idioma ativo, sem frases híbridas em inglês/português.
- Validação: 351 testes Python executados, 350 aprovados e um symlink ignorado pela restrição do Windows; os doze arquivos JavaScript passaram. A nova cobertura verifica os dois idiomas, as APIs exatas, sucesso, falha e traduções dos tooltips. Nenhum build portátil foi gerado.

## v0.35.0 — 01/09/2026

- A primeira abertura agora começa com **Select language**, permitindo escolher Português ou English antes de qualquer orientação. A escolha fica salva, altera toda a interface do Manager e pode ser modificada depois nas Configurações.
- Adicionado um tutorial inicial bilíngue de seis etapas para configuração da pasta do jogo, importação, ativação e componentes, organização, conflitos/segurança e backups. **Review tutorial** reinicia o guia; **I understand** confirma a conclusão e impede novas aberturas automáticas.
- Configurações ganhou a seção **Idioma / Language** e a ação **Rever tutorial**. A preferência altera toda a interface — navegação, modais, conteúdo dinâmico, mensagens, confirmações e visualizador — e uma revisão usa imediatamente o idioma selecionado.
- Validação: 122 testes Python executados, 121 aprovados e um symlink ignorado pela restrição do Windows; os onze arquivos JavaScript passaram. A cobertura inclui persistência independente de idioma/conclusão, troca global Português/English, textos dinâmicos, alertas, confirmações, migração de configurações, backups, recuperação, importação e empacotamento. Nenhum build portátil foi gerado.

## v0.34.3 — 01/09/2026

- A opção de guardar o compactado agora também cria um ZIP quando a importação recebe PAK/UCAS/UTOC soltos. O ZIP é salvo em `Archive` dentro da pasta privada do mod, junto da cópia instalável já existente.
- Seleções com vários pacotes são reunidas no mesmo ZIP. Cada trio usa uma subpasta numerada quando necessário, preservando arquivos homônimos sem colisão.
- A criação do ZIP participa do progresso e do cancelamento da importação. As origens continuam sendo apagadas somente após arquivos privados, arquivos ativos e catálogo serem confirmados; desativar a preferência conserva apenas a cópia instalável normal.

## v0.34.2 — 01/09/2026

- As abas **Variações** e **Complementos** nos detalhes agora permanecem selecionadas quando uma caixa, switch, rótulo ou outra ação atualiza a lista de componentes. A renderização anterior sempre recriava o filtro em **Todos**.
- A aba é guardada separadamente para cada mod durante a sessão. Voltar aos detalhes do mesmo mod conserva sua última escolha sem alterar o cadastro ou criar uma preferência persistente em disco.
- Validação: 348 testes Python executados, 347 aprovados e um symlink ignorado pela restrição do Windows; os dez arquivos JavaScript passaram. A cobertura confirma a restauração de **Complementos**, a troca para **Variações** e uma nova renderização. Nenhum build portátil foi gerado.

## v0.34.1 — 01/09/2026

- O popup aberto pelo alerta de conflito em um card agora mostra **Desativar mod** ao lado de cada concorrente ativo. A ação desliga somente o concorrente escolhido e mantém ativo o mod cujo alerta foi aberto.
- Depois da desativação, cards, popup e relatório em cache são revalidados imediatamente; a atualização automática do detector continua em segundo plano. Se o jogo estiver aberto e o bloqueio de operações impedir a mudança, nenhum estado local é alterado e o erro permanece visível para o usuário.
- A lista acomoda nomes extensos e leva o botão para uma linha própria em janelas estreitas. O texto também deixa explícito qual mod continuará ativo.
- Validação: 348 testes Python executados, 347 aprovados e um symlink ignorado pela restrição do Windows; os dez arquivos JavaScript passaram. Os indicadores de conflito agora têm 19 cenários, incluindo sucesso e falha da nova ação. Nenhum build portátil foi gerado.

## v0.34.0 — 01/09/2026

- Configurações ganhou **Arquivos da importação**, com preferências independentes para guardar uma cópia do ZIP/RAR/7z na biblioteca privada e para apagar ou manter as origens após uma instalação bem-sucedida.
- Desativar o backup do compactado economiza espaço em `mods_storage`, mas conserva os PAK/UCAS/UTOC necessários ao mod e os metadados do nome de origem. PAKs de áudio necessários à prévia continuam privados porque fazem parte do funcionamento, não de um backup opcional.
- A limpeza de origem agora segue a mesma regra para ZIP/RAR/7z, PAK/UCAS/UTOC soltos e imagens escolhidas. Com a preferência desmarcada, todos permanecem no local original; com ela marcada, só são apagados depois que arquivos privados, arquivos ativos e catálogo foram confirmados. Cancelamento, falha, mudança detectada no arquivo e origens dentro de `mods_storage` continuam preservando os dados.
- As duas opções começam marcadas. Isso mantém o comportamento anterior para compactados e imagens e passa a aplicar a mesma limpeza aos pacotes soltos; a cópia instalável da biblioteca existe independentemente dessas escolhas.
- Validação: 348 testes Python executados, 347 aprovados e um symlink ignorado pela restrição do Windows; os dez arquivos JavaScript passaram. A cobertura inclui as combinações guardar/apagar, compactado sem backup, origem mantida com imagem, pacote solto e fluxo transacional existente. Nenhum build portátil foi gerado.

## v0.33.0 — 01/09/2026

- Componentes existentes agora podem receber uma atualização pelo menu `⋯`. O usuário escolhe um único pacote; o Manager mantém ID, nome, rótulo, posição, relações e estado do componente e guarda o conteúdo anterior num histórico restaurável.
- Ao anexar variantes pelo `+` ou por arrastar arquivos sobre a seção Componentes, o Manager compara assets internos e nomes. Uma possível atualização é somente sugerida para revisão: aceitar substitui o componente indicado; recusar conserva o novo pacote como variante desativada.
- Remoção de componente ganhou revisão de dependências e recuperação. O último componente não pode ser removido, requisitos em uso bloqueiam a ação e os arquivos privados permanecem disponíveis em **Restaurar**. Versões e componentes removidos também entram na verificação de integridade e no backup completo sem afetar classificação, conflitos ou arquivos ativos.
- Cada componente novo registra data, tamanho, origem e hash agregado. A tela mostra esses dados e o Histórico apresenta as últimas medições de importação separando backend, recarga da biblioteca e abertura dos detalhes, para diagnosticar a pausa de 20–30 segundos relatada.
- Validação: 344 testes Python executados, 343 aprovados e um symlink ignorado pela restrição do Windows; os dez arquivos JavaScript passaram. Foram testados sugestão sem aplicação automática, atualização/restauração de payload, remoção/restauração, dependências, integridade, backup, medição de desempenho e retomada do job. Nenhum build portátil foi gerado, conforme solicitado.

## v0.32.1 — 01/09/2026

- Adicionado um botão `+` ao lado de **Componentes** nos detalhes de mods PAK. Ele aceita PAK/UCAS/UTOC e ZIP/RAR/7z para anexar variantes esquecidas ou publicadas depois, sem criar outro mod nem alterar identidade, pasta, tags, prioridade, mídia ou componentes existentes.
- Novos componentes são analisados e guardados isoladamente em `Components/<id>/`, começam desativados e só chegam à pasta ativa quando o usuário liga seu switch. Duplicatas exatas por hash/tamanho/tipo são ignoradas; se toda a seleção já existir, nenhuma alteração é feita.
- O anexo usa job com progresso, cancelamento antes da confirmação, journal de recuperação e preservação do compactado original. A origem só é removida depois que arquivos privados e catálogo são confirmados. Background, ReShade, áudio de Background e mods externos continuam usando seus fluxos próprios.
- Validação: 339 testes Python executados, 338 aprovados e um symlink ignorado pela restrição do Windows; os nove arquivos JavaScript passaram. A cobertura inclui anexo desativado, ativação posterior, duplicata sem mudança, fluxo completo pelo seletor/API e ausência de recuperação pendente. Nenhum build portátil foi gerado nesta versão, conforme solicitado.

## v0.32.0 — 31/08/2026

- Componentes de áudio de Background passam a usar os metadados estruturais da importação para receber `Audio`, evitando `Unknown` sem depender do nome do arquivo ou de correção manual. Tipos continuam cumulativos e componentes comuns não recebem essa classificação fora de um registro de Background.
- A listagem de classificações pendentes reutiliza as raízes resolvidas da biblioteca e da pasta ativa durante cada mod. Na biblioteca real de 296 mods e 2.461 componentes, a etapa caiu para cerca de 4,3 s; tela principal ficou em cerca de 0,21 s, detalhes no pior caso em 0,73 s e capas frias no pior caso em 1,0 s. O atraso de 20–30 s não foi reproduzido no backend.
- Catálogo Rivalskins atualizado para 691 skins, incluindo seis IDs novos; testes verificam IDs, nomes, duplicatas e recolors. O mapping local continua compatível com o build 3805839/S9.5 do jogo.
- Removida da interface a ação experimental de envio ao Repak. O suporte de compactados e a instalação do Manager permanecem inalterados.
- A prévia BK2 agora detecta somente um Bink Player disponível no `PATH` e aparece desativada quando ele não existe. Caminhos particulares do computador de desenvolvimento foram removidos; importar, ativar e organizar Background não depende do player.
- Acrescentados `LICENSE` e `NOTICE` do CUE4Parse no commit usado pelo extrator. Um script e lock reproduzíveis preparam, sem executar os downloads, um arquivo separado com as fontes exatas de CUE4Parse, UAssetToolRivals, HandBrake 1.11.2 e 7-Zip 26.02.
- Validação automatizada: 336 testes Python executados, com 335 aprovados e um ignorado pela restrição de symlink real no Windows; os nove arquivos JavaScript passaram. Dependências fixadas e runtimes 3D foram verificados offline, e os hashes de `mods.json` e `settings.json` permaneceram iguais durante os benchmarks somente leitura.
- Validação reversível no jogo: desativar e reativar uma variante aninhada Mesh/Texture/Physics removeu e restaurou os três arquivos PAK/UCAS/UTOC com hashes idênticos. O Marvel Rivals build 1.1.3805839 iniciou pelo launcher sem exigir patch; a inspeção visual dentro da janela protegida ficou pendente por falta de autorização do controle de tela. O perfil temporário foi aplicado e excluído ao final.
- A distribuição continua privada: licença/EULA do código próprio, assinatura, direitos de Oodle/ícones/catálogos/marcas, correspondência reproduzível do binário UAssetTool e teste físico em outro computador ainda são portões antes de publicar ou comercializar.

## v0.31.0 — 31/08/2026

- Visualizador 3D independente da instalação do FModel: preparação automática de mapping e codecs pelo Manager, com fontes HTTPS controladas, hashes verificados, limites de tamanho e cache privado. Atualização explícita em Configurações; falhas e cancelamento preservam o suporte anterior, sem invalidar prévias quando os arquivos não mudam.
- Removidos o seletor/configuração e a API de abertura do FModel. Configurações antigas são preservadas no JSON, mas seus caminhos não são consultados pelo visualizador. A primeira preparação precisa de internet; o suporte instalado funciona offline. A pasta do jogo ainda fornece as dependências dos modelos.
- Extrator publicado com .NET próprio (win-x64 self-contained). Containers são lidos diretamente na origem, inclusive em outro disco, sem cópias/hardlinks. Texturas PNG usam decoder gerenciado; blocos BC seguem diretamente para GPUs compatíveis.
- Distribuição portátil para Windows 11 x64, com Python, WebView2, .NET 8 privado para UAssetTool, .NET do leitor 3D, 7-Zip, vgmstream e HandBrakeCLI. Conversão de vídeo usa parâmetros internos, sem exigir um perfil salvo no HandBrake de outro usuário. O diagnóstico `--self-check` testa os leitores com ambiente isolado.
- Build por lista permitida, hashes e manifesto de distribuição, sem catálogo, configurações pessoais, mods, caches ou SDKs de desenvolvimento. Fontes/termos das dependências estão documentados; o pacote foi preparado localmente, sem publicação.
- Empacotamento final reprodutível em ZIP, com ordem/data/permissões canônicas, SHA-256 adjacente e metadados verificáveis. O gerador recusa bundles executados ou alterados, não sobrescreve releases e não publica arquivos. Checklist de liberação e modelo de relatório de erro registram os portões de privacidade, assinatura, fontes correspondentes e direitos de terceiros.
- A prévia de vídeos BK2 continua opcional e dependente de Bink Player; o aviso agora explica isso sem apontar uma pasta particular do computador do desenvolvedor. Importação/ativação de Background não exige esse player.
- Validação: preparação real do suporte sem FModel; exportação de um componente com PNG e texturas de GPU, sem PATH/.NET externo e sem falhas; análise de 16 assets pelo leitor com runtime privado. Catálogo, configurações e arquivos do jogo não foram alterados. A validação dentro do jogo permanece pendente por escolha do usuário.

## v0.30.2 — 31/08/2026

- Corrigidos alertas de conflitos que permaneciam após desligar um mod ou componente. O relatório em cache é filtrado pelo estado ativo atual antes da exibição: remove a disputa encerrada dos dois oponentes, preserva outras disputas e recalcula contagens, prioridades, empates e vencedores.
- Respostas iniciadas antes de uma mudança de estado não substituem resultados atuais. Uma atualização solicitada durante outra verificação continua na fila; resultados vazios também contam como verificação realizada, permitindo recalcular ao reativar um mod.
- Popups revalidam os participantes ao abrir, relatórios abertos acompanham as mudanças e retomar um job de conflitos consulta o estado atual em vez de reaplicar uma resposta antiga.
- A política do detector no backend permanece inalterada, incluindo Physics fora da disputa e as regras de identidade/principal-acompanhamento restauradas anteriormente. Um mod inteiro desligado não participa, mesmo quando suas seleções internas de componentes continuam ligadas.
- Validação: 39 testes Python de conflitos/resolução e os nove arquivos JavaScript passaram; `test_conflict_indicators.mjs` cobre 17 cenários. A reprodução confirmou que o alerta vinha de uma resposta antiga na interface, enquanto a consulta seguinte do backend retornava zero conflitos. Nenhum dado real foi alterado e o jogo não foi aberto.
- Revisão da interface com biblioteca temporária: dois conflitos ativos desapareceram dos dois cards ao desligar um participante; a checagem seguinte retornou zero. Reativar o mod restaurou os dois avisos, sem precisar reiniciar a interface.

## v0.30.1 — 31/08/2026

- Os detalhes abrem imediatamente em estado de carregamento e recebem os metadados sem esperar as imagens. A galeria carrega em segundo plano com dois workers e cache de 48 revisões; ações como Corrigir permanecem disponíveis enquanto as imagens carregam. Falhas na consulta dos detalhes oferecem a opção de tentar novamente.
- Capas já carregadas são reaproveitadas quando o ID do mod e a revisão da mídia correspondem. A lista agenda somente cartões visíveis ou próximos, com fallback para WebViews sem IntersectionObserver, e pausa novos pedidos enquanto os detalhes estão abertos. Filas obsoletas são descartadas sem interromper workers válidos; respostas de revisões antigas não substituem a capa atual.
- Fechar, trocar de mod, repetir cliques ou atualizar detalhes simultaneamente não permite que uma resposta atrasada reabra ou substitua a seleção mais recente. A galeria aproveita a capa já disponível e não dispara reanálise dos componentes já classificados.
- Validação: 285 testes Python executados, com 284 aprovados e um symlink real ignorado por restrição do Windows; os nove arquivos de regressão JavaScript passaram. A interface foi conferida com seis imagens e atrasos artificiais de 1 s nos metadados e 4 s nas prévias: carregamento visível imediatamente, Corrigir utilizável antes de todas as imagens e troca/fechamento respeitados.
- A demora relatada de 20–30 s após uma importação não foi reproduzida exatamente no WebView real. Leituras isoladas de metadados e decodificação de imagens não medem esse tempo; falta observar a próxima importação real. Não houve alteração de dados reais nem abertura do jogo.

## v0.30.0 — 31/08/2026

- O acompanhamento de operações usa identificadores de pedido idempotentes. A interface reencontra a tarefa após uma resposta perdida ou recarregamento, inclusive uma seleção de importação já preparada, sem iniciar outra cópia. A confirmação de instalação, backup e extração retorna a mesma tarefa quando repetida; o formulário continua sem lista de prévia de componentes.
- ReShade, Background e áudio de Background passam a ter preparação/cópia canceláveis e aplicação com registro durável. O MoviesBink original é preservado antes da publicação; falhas restauram os arquivos afetados ou ficam disponíveis para recuperação revisada. Camadas ou arquivos alterados posteriormente impedem uma restauração incompatível. O cancelamento permanece bloqueado durante a aplicação final.
- Verificação de hashes e busca de conflitos executam em segundo plano com progresso e cancelamento. A política e o relatório de conflitos restaurados em v0.29.0 permanecem, incluindo Physics fora da disputa e exigência de mesmo personagem/skin nos conflitos automáticos entre mods.
- Correções pessoais podem ser reaproveitadas na reimportação mediante revisão. A correspondência usa hashes do conteúdo: identidade exige o conjunto completo, e nomes, rótulos e relações exigem componentes identificados sem ambiguidade. As preferências ficam em `personal_corrections.json`, independentes da existência do mod; nomes de arquivos sozinhos não aplicam correções nem criam dependências.
- Adicionado backup completo opcional em ZIP64, sem recompressão, com estimativa de espaço, progresso, cancelamento e manifesto SHA-256. Inclui catálogo/configurações, correções pessoais, arquivos privados, mídias, compactados preservados e MoviesBink original quando disponível. Arquivos cadastrados disponíveis somente no jogo também são copiados; ausências são listadas e exigem confirmação explícita para gerar uma cópia incompleta.
- A extração de backup completo verifica os hashes e cria somente uma nova pasta, com mods desativados e caminho do jogo vazio. Snapshots originais permanecem em `catalog/`; a biblioteca atual e o jogo não são substituídos. Destinos existentes, links/junctions e caminhos inseguros são recusados. O backup leve do catálogo continua disponível separadamente.
- A tela principal recebe um snapshot com uma leitura de `mods.json` e uma de `settings.json`, reaproveitando os dados para listas e filtros. O cache de assets fica fora somente dessa resposta; o detalhe e a persistência continuam completos. A enumeração de pastas usa `scandir` sem seguir links/junctions. Incluído benchmark sintético reproduzível em `tests/benchmark_library.py`.
- Validação: a suíte Python executou 272 testes, com 271 aprovados e um teste de symlink real ignorado por restrição do Windows; os casos de reparse/junction e links em ZIP são cobertos separadamente. Os sete arquivos de regressão JavaScript passaram, incluindo 21 cenários de acompanhamento e 15 das ferramentas da biblioteca; compilação Python e sintaxe JavaScript também passaram. Reimportação com correções, retomada da seleção após recarregar, cancelamento e criação/extração de backup completo foram revisados com biblioteca temporária. A validação dentro do jogo permanece pendente por escolha do usuário; não houve migração em massa nem alteração de mods reais.
- Limites: o acompanhamento reencontra tarefas na mesma sessão Python, mantendo até 64 resultados terminais; ao reiniciar o aplicativo, a recuperação usa os registros duráveis, sem reenviar a importação automaticamente. Rascunhos dos campos do formulário não são preservados e ofertas de correção exigem nova revisão. A recuperação ampliada cobre importações especiais, não todos os switches antigos ou alterações de regras. O backup não inclui o executável do Manager, caches regeneráveis ou outros backups.
- Os fluxos de integridade e conflitos também foram conferidos na interface com dados temporários: progresso, resultados esperados e indicadores preservados. O teste de integridade manteve a distinção entre cópia ausente e divergente; o de conflitos respeitou os personagens/skins e o relatório anterior.

## v0.29.0 — 30/08/2026

- Removida a prévia de importação adicionada em v0.28.0. O formulário volta a mostrar os dados do mod e o destino, sem a lista de componentes; análise, hashes e isolamento dos arquivos continuam no backend.
- Restaurados o detector e o relatório de conflitos anteriores à v0.28.0: Physics fica fora da disputa, principal/acompanhamento segue a regra anterior e conflitos automáticos entre mods exigem o mesmo personagem e skin. Os novos filtros e ações por responsável foram retirados; cache e contagem sem duplicatas foram preservados.
- Adicionada a opção separada “Escolher o que manter”: ela usa os conflitos do detector restaurado e mostra as desativações e consequências para dependentes antes de aplicar. A operação revalida o plano e registra os arquivos e o catálogo para recuperação se for interrompida.
- Importações de PAK/UTOC/UCAS e ZIP/RAR/7z executam preparação e cópia em segundo plano, com etapas, progresso e cancelamento seguro antes da aplicação final. O cancelamento fica bloqueado durante a conclusão; fontes só são removidas após sucesso e são preservadas se mudarem durante a operação.
- Importações de pacotes, aplicação de perfis, alterações de estado em lote e resolução assistida de conflitos passam a usar registros duráveis de operação. Ao reabrir, preparações abandonadas ou alterações incompletas aparecem para revisão e recuperação; operações ainda em execução não são oferecidas para recuperação por outra instância.
- Ampliada a verificação sob demanda da biblioteca: arquivos privados/ativos/mídias ausentes, hashes divergentes, falhas de acesso e pastas sem vínculo com o catálogo. O reparo exige revisão, restaura somente destinos ausentes e nunca sobrescreve arquivos existentes nem apaga sobras. Registros antigos sem hash de referência são identificados sem inventar uma referência.
- Nova tela de classificações pendentes reúne arquivos ausentes, leituras pendentes, falhas de leitura e tipos não reconhecidos. A reanálise processa somente os componentes selecionados, informa falhas individuais e preserva identidade, nomes, ordem e switches.
- Sugestões de relações identificam alternativas como Mask On/Mask Off e possíveis complementos Physics. Toda sugestão exige revisão das regras e dos estados afetados; nomes não criam dependências automaticamente.
- Ações secundárias dos componentes foram reunidas no menu “⋯”, com filtros visuais de Variações/Complementos quando aplicáveis e textos em português. Trocas que afetam vários componentes atualizam todos os switches envolvidos; a barra de ações em lote fica oculta quando não há seleção.
- O símbolo × ao lado de “Marvel Manager” na barra de título foi substituído por uma silhueta SVG de caranguejo vermelho.
- Validação automatizada: 159 testes Python e os seis arquivos de testes JavaScript passaram; os novos fluxos foram revisados no navegador com biblioteca temporária. A validação dentro do Marvel Rivals permanece pendente por escolha do usuário; não houve migração da biblioteca nem alteração de mods reais nesta entrega. ReShade/Background mantêm seus importadores próprios, sem a mesma cobertura de cancelamento e recuperação dos pacotes PAK.

## v0.28.0 — 30/08/2026

- Novas importações isolam cada trio PAK/UTOC/UCAS em `Components/<id>/`, tanto na biblioteca privada quanto na pasta ativa, preservando os nomes originais. Compactados homônimos também ficam separados. Bibliotecas antigas continuam compatíveis, sem migração em massa; arquivos sobrescritos antes desta versão não podem ser recuperados automaticamente.
- `mods.json` e `settings.json` usam gravação atômica com flush/fsync, bloqueio entre gravadores e mesclagem de alterações independentes. Edições concorrentes incompatíveis são reportadas em vez de sobrescritas silenciosamente.
- Prévia de importação mostra compactados, componentes, arquivos, tamanho, tipos e identidade sugerida. Hashes detectam conteúdo idêntico na seleção/biblioteca; switches definem o estado inicial, inclusive todos desativados. Fontes alteradas após a prévia são rejeitadas.
- O botão Diagnóstico mostra estado da leitura, exemplos dos assets que sustentam cada tipo e identidade detectada versus seleção salva. Há reanálise explícita por componente; falhas de leitura e arquivos ausentes são distintos de tipo não reconhecido.
- O botão Relações permite grupos de alternativas e dependências entre componentes do mesmo mod. A ativação acompanha requisitos e desativa alternativas/dependentes; ciclos e requisitos incompatíveis são rejeitados. Perfis validam essas regras antes de alterar arquivos. Falhas ao salvar switches restauram os arquivos do estado anterior.
- Conflitos mostram caminhos de assets e pacotes envolvidos, filtros por texto/tipo/empate e ações para abrir o mod ou desativar um concorrente. Duas variantes Mesh são identificadas mesmo dentro do mesmo mod; relações declaradas são respeitadas. Identidades diferentes não escondem sobreposições reais entre mods.
- A interface esclarece que prioridade representa a preferência do Manager e não controla a ordem de carregamento do jogo. Os contadores não duplicam um asset quando um mod tem vários componentes envolvidos.
- Remover um mod preserva os compactados e mídias; somente a exclusão permanente elimina todos os dados privados.

## v0.27.7 — 30/08/2026

- Os seletores e a importação aceitam compactados `.7z`, além de ZIP/RAR, incluindo seleção múltipla e preservação dos originais na biblioteca. A extração usa WinRAR ou 7-Zip; UnRAR permanece restrito a RAR.
- Compactados sem pacotes instaláveis são identificados pelo nome na mensagem de erro, sem ignorá-los numa seleção múltipla. Falhas na preparação limpam os temporários sem apagar as fontes; extrações incompletas não são aceitas como sucesso.

## v0.27.6 — 30/08/2026

- A importação classifica os assets de cada componente, incluindo variações desativadas, e salva o cache individual; o tipo do mod reúne os tipos dos seus pacotes.
- Registros antigos completam automaticamente a análise após a exibição dos detalhes, com atualização dos badges e do botão 3D sem correção manual. A análise preserva switches, ordem, nomes, mídias e identidade.
- O cache evita novas leituras ao reabrir os detalhes ou alternar componentes e é invalidado quando os arquivos mudam. Falhas de leitura mantêm a classificação existente e permitem nova tentativa após um minuto; Unknown continua válido quando não há evidência suficiente.

## v0.27.5 — 30/08/2026

- A classificação de componentes reaproveita também os assets já lidos pelo detector de conflitos, evitando Unknown quando há evidência disponível sem reanalisar os pacotes ao abrir os detalhes.

## v0.27.4 — 30/08/2026

- Corrigida a identificação de Sue Storm/Susan Storm como Mulher Invisível nos nomes de pacotes, evitando confusão com Tempestade.
- A sugestão de importação passa a usar a seleção de identidade por assets já existente, priorizando malhas sobre materiais compartilhados para determinar a skin.

## v0.27.3 — 30/08/2026

- Corrigido o zoom do visualizador 3D que só aparecia após girar o modelo. Eventos de mudança da câmera agora solicitam o redesenho no próximo frame, inclusive roda do mouse e pinch, mantendo a renderização ociosa e as otimizações de carregamento.

## v0.27.2 — 30/08/2026

- A primeira abertura 3D prepara apenas a variante selecionada, sem esperar todas as versões do componente; o seletor continua disponibilizando os demais modelos.
- A geometria usa os vértices e índices existentes, preservando triângulos, normais, tangentes e UVs, sem reduzir o modelo. O visualizador deixa de renderizar continuamente quando a câmera e a cena estão paradas.
- Texturas e materiais são deduplicados, inclusive referências equivalentes `Game/` e `Marvel/Content/`. Variantes reutilizam as imagens já preparadas.
- Texturas BC suportadas pela GPU usam os blocos originais, sem conversão para PNG. Mipmaps ausentes são gerados na GPU para manter a filtragem; formatos não compatíveis e normal maps continuam com o caminho PNG sem perda.
- Removida a análise redundante pelo UAssetTool antes da prévia; o extrator consulta diretamente apenas os pacotes do componente. O catálogo e os mods ativos não são modificados por essa leitura.
- Esc/fechar cancela a preparação, sem deixar uma conversão antiga segurando a próxima. O cache valida também a presença das texturas e não aceita resultados de uma conversão incompleta.
- Validação sem cache: preparação do SuperBuu caiu de mais de 120 s para 3,4 s; Peni, de 106,8 s para 3,5 s; Lopunny, de 9,4 s para 1,8 s. No teste integrado, do clique até aparecer com texturas: 4,7 s, 4,3 s e 2,3 s, respectivamente. As medidas variam conforme o modelo e o sistema.

## v0.27.1 — 29/08/2026

- Corrigida a classificação parcial de componentes únicos: Mesh, Texture e Physics do mesmo pacote não ficam reduzidos ao tipo Physics salvo anteriormente.
- Os detalhes reaproveitam caches de assets atuais e legados sem nova varredura; AnimBlueprint/Skeleton com prefixo SK não são considerados Mesh por esse prefixo.

## v0.27.0 — 29/08/2026

- Reclassificados os componentes existentes: Mesh permanece principal; Physics, Texture e UI são cumulativos e complementares; pacotes com `AnimBlueprint` passam a indicar Physics.
- Busca, personagem, skin, tipos, pasta e tags agora funcionam como filtros cumulativos, com contagens recalculadas conforme os demais filtros ativos.
- Perfis salvos ganharam o botão `Atualizar`, que substitui seu snapshot pelo estado atual de mods, prioridades e componentes; o fluxo foi validado com os 270 mods atuais.
- Prioridades agora explicam visualmente quando resolvem um conflito e quando ainda existe empate.
- O histórico registra e filtra ações relevantes e permite limpar tudo ou somente entradas anteriores a 30 dias.
- O visualizador 3D deixou de percorrer todo o pacote global de personagens: somente assets do componente e texturas necessárias são processados, mantendo as dependências globais montadas para resolução.
- A primeira abertura 3D medida caiu para 18,7 segundos no componente de validação; a reabertura pelo cache levou 0,085 segundo.

## v0.26.4 — 29/08/2026

- Removido o botão FModel dos componentes Mesh; o acesso permanece somente pelo visualizador 3D nativo do Manager.

## v0.26.3 — 29/08/2026

- Corrigidos modelos 3D que apareciam pretos ou excessivamente metálicos: vertex colors usados pelo jogo como máscaras não escurecem mais a textura no visualizador.
- O extrator agora inclui as texturas pertencentes ao componente mesmo quando materiais personalizados usam nomes diferentes, associando conjuntos Body/Equip e canais UV quando necessário.
- Ajustados normal/specular/ORM, metalness e a iluminação indireta para preservar as cores do diffuse sem perder a leitura do volume.
- Dependências de materiais do pacote de personagens do jogo são montadas por hardlink temporário, sem duplicar o arquivo de 15 GB no cache.

## v0.26.2 — 29/08/2026

- Corrigida a classificação de componentes antigos que permaneciam como `Unknown`: componentes únicos reutilizam os tipos confirmados do mod e conjuntos antigos reconhecem Mesh quando aplicável.

## v0.26.1 — 29/08/2026

- A seção `Components` agora aparece também nos mods com apenas um componente, mantendo disponível a visualização, classificação e ações desse componente.

## v0.26.0 — 29/08/2026

- Adicionado o visualizador 3D interno ao botão `3D` de cada componente classificado como Mesh, inclusive quando o mod possui somente um componente.
- O Manager agora lê sob demanda o PAK/UTOC/UCAS do componente escolhido, extrai os Skeletal/Static Meshes e aplica as texturas encontradas sem abrir uma janela externa.
- O visualizador permite girar, aproximar, mover, centralizar, alternar modelos, texturas e wireframe; `Esc` fecha somente a visualização 3D e mantém os detalhes do mod abertos.
- A preparação pesada não ocorre ao abrir os detalhes: ela começa apenas ao clicar em `3D`, possui limite de tempo e guarda o resultado em cache no disco D para tornar as próximas aberturas rápidas.
- Incluídos o runtime local do extrator e os módulos Three.js necessários, evitando exigir uma instalação separada do .NET para usar a visualização.

## v0.25.40 — 29/08/2026

- A abertura dos detalhes não executa mais a leitura pesada de UTOC/PAK para todos os componentes. Os tipos já salvos (ou inferidos pelo nome em registros antigos) são mostrados imediatamente; a leitura interna continua sob demanda no botão “Conteúdo” do componente escolhido.

## v0.25.39 — 29/08/2026

- Removido o botão e a integração experimental de prévia 3D por GLB; o botão FModel permanece disponível para componentes Mesh.

## v0.25.38 — 28/08/2026

- Tornado o “Scan installed mods” leve: ele descobre pacotes sem abrir cada UTOC/PAK com UAssetTool. A análise profunda ocorre somente ao abrir os detalhes do mod.

## v0.25.37 — 27/08/2026

- O botão FModel de componentes Mesh agora abre o `.utoc` correspondente diretamente, mantendo a validação do `.ucas` pareado.

## v0.25.36 — 27/08/2026

- Removida a integração experimental com UModel após a incompatibilidade com os pacotes testados.

## v0.25.35 — 27/08/2026

- Adicionada integração de teste com UModel: caminho configurável e abertura direta do PAK/UTOC/UCAS do componente Mesh, sem conversão ou cópias temporárias.

## v0.25.34 — 27/08/2026

- Adicionado visualizador 3D nativo para modelos `.glb` vinculados a componentes Mesh, com rotação, zoom e cópia privada do modelo na biblioteca.

## v0.25.33 — 27/08/2026

- O caminho do FModel agora pode ser definido selecionando sua pasta (o Manager encontra `FModel.exe`) ou colando o caminho completo manualmente.

## v0.25.32 — 27/08/2026

- Corrigido o seletor de FModel.exe nas Configurações, com validação após a escolha do arquivo.

## v0.25.31 — 27/08/2026

- Adicionada integração inicial com FModel: caminho configurável e botão 3D para componentes Mesh.

## v0.25.30 — 27/08/2026

- Mods com Jiggle ou Skeleton AnimBlueprint agora recebem o tipo Physics também no card da biblioteca.

## v0.25.29 — 27/08/2026

- Componentes `SK_...AnimBlueprint` não são mais classificados automaticamente como Mesh; somente assets de malha reais recebem esse tipo.
- `Jiggle` e Skeleton AnimBlueprint são identificados como Physics.

## v0.25.28 — 27/08/2026

- Physics e UI deixam de ser classificados como Mesh quando o nome do componente indica explicitamente esses tipos; ambos aparecem como acompanhamentos.

## v0.25.27 — 27/08/2026

- A seleção de componentes é preservada ao entrar em Editar ordem, permitindo arrastar vários selecionados como um grupo.
- Nomes exibidos removem o caminho/prefixo do ZIP e mostram o tipo detectado do componente.
- Todos os componentes Mesh agora são marcados como Principal; os tipos aparecem em badges ao lado dos controles.
- Registros antigos agora recalculam o tipo de cada componente ao abrir os detalhes.
- Badges de tipo dos componentes receberam o mesmo estilo visual dos badges principais.

## v0.25.26 — 25/08/2026

- Componentes de textura agora são reconhecidos como acompanhamentos e aparecem no fim da lista, junto dos componentes Physics.

## v0.25.25 — 24/08/2026

- Corrigida a prévia de áudio de Background para usar o PAK de origem do componente, em vez de sempre consultar o primeiro PAK do pacote.
- O seletor de áudio preserva o nome original do PAK, facilitando distinguir testes com vários bancos Asgard.

## v0.25.24 — 24/08/2026

- Nos detalhes de Background, setas ou WASD agora percorrem exclusivamente as prévias de Cinematics, ignorando switches, áudio e botões de remoção. A prévia selecionada recebe destaque visual.

## v0.25.23 — 23/08/2026

- Corrigido o filtro de áudio das cinematics de Garden: bancos antigos agora têm o mapa identificado pelo nome do banco mesmo quando o registro salvo não tinha essa localização.

## v0.25.22 — 23/08/2026

- Cards de Background agora mostram o tamanho total incluindo complementos relacionados, abreviado em GB quando necessário para não sobrepor os controles.

## v0.25.21 — 23/08/2026

- Corrigido o fechamento do seletor de áudio com `Esc`: agora somente o seletor é fechado, mantendo aberto o detalhe do mod.

## v0.25.20 — 23/08/2026

- Adicionado controle de volume global e persistente para prévias de áudio e vídeo, acessível diretamente na barra superior.

## v0.25.19 — 23/08/2026

- Bancos de áudio só são copiados para o jogo quando uma cinematic vinculada estiver ativa; permanecer selecionado sem cinematic ativa não instala o PAK.
- Grupos de áudio no seletor agora podem ser renomeados ou removidos diretamente.

## v0.25.18 — 23/08/2026

- Corrigida a prévia de bancos Wwise: o player agora extrai a faixa interna do `.bnk` selecionado, em vez de repetir a primeira faixa externa do pacote.

## v0.25.17 — 23/08/2026

- Cinematics com áudio vinculado agora permitem desvincular o banco diretamente no cartão.
- A prévia de áudio passou para o seletor de bancos e toca dentro do Manager, sem abrir player ou visualizador externo.

## v0.25.16 — 23/08/2026

- O seletor de áudio passa a mostrar somente bancos do mesmo mapa/Location da cinematic escolhida, evitando listas enormes e opções sem relação.

## v0.25.15 — 23/08/2026

- Corrigida a listagem visual de bancos de áudio: grupos e cartões agora recebem os nomes reais salvos no pacote, incluindo `Edits 2`.

## v0.25.14 — 23/08/2026

- O seletor de áudio agora é visual: pacotes ficam em grupos expansíveis e cada banco pode ser escolhido por cartão, sem precisar digitar números.

## v0.25.13 — 23/08/2026

- Áudio de Background agora é vinculado e controlado no próprio cartão de cada cinematic, sem lista separada.
- Alterações de bancos Wwise solicitadas com o jogo aberto ficam em fila persistente e são aplicadas ao fechar o Marvel Rivals.
- Adicionada prévia de áudio por vgmstream para os PAKs de áudio importados.

## v0.25.12 — 23/08/2026

- Backgrounds agora aceitam PAKs de áudio vinculados. Os bancos Wwise internos são separados em componentes individuais, começam desligados e informam o mapa/variação da cinematic afetada antes da ativação.

## v0.25.11 — 23/08/2026

- No visualizador da galeria, a roda do mouse agora troca a mídia exibida. Sobre a faixa inferior, ela percorre horizontalmente as miniaturas.

## v0.25.10 — 23/08/2026

- Criar backup agora salva diretamente em `backups` do Marvel Manager com nomes sequenciais, como `marvel-manager-backup1.json`, `marvel-manager-backup2.json`, sem sobrescrever os backups existentes.

## v0.25.9 — 23/08/2026

- Corrigida a aplicação de Cinematics de Background: um complemento sem vídeos selecionados não envia mais todos os seus BK2 para o jogo. Apenas o vídeo marcado no switch individual pode substituir a versão ativa.

## v0.25.8 — 23/08/2026

- Cinematics de Entrada, Fim e Carregamento passaram a ser agrupadas primeiro pelo mapa. Dentro de cada mapa, os grupos mostram seus respectivos vídeos de Entrada da partida, Fim da partida e Carregamento da partida.

## v0.25.7 — 23/08/2026

- Arquivos na pasta `Movies\\League` (como `MRC` e `MRC CN`) agora aparecem em `Esportes`, separados das telas de Inicialização do jogo.

## v0.25.6 — 23/08/2026

- Complementos de Background agora chegam com todas as cinematics desmarcadas. Ativar o complemento apenas disponibiliza as prévias; cada vídeo só substitui o atual quando seu switch individual for escolhido.
- Complementos antigos ainda sem essa marca são convertidos na próxima ativação, sem desligar as escolhas já feitas nos complementos que já passaram por esse fluxo.

## v0.25.5 — 22/08/2026

- A galeria de Cinematics agora usa categorias descritivas e ordenadas: Entrada da partida, Fim da partida, Vídeos dos telões, Carregamento da partida, Login e Lobby e Inicialização do jogo.
- Cada cartão informa sua função (ataque/defesa, carregamento, tela de login, transição, tela inicial ou abertura), enquanto os nomes dos arquivos e Locations continuam visíveis.
- `Outros` foi renomeado para `Inicialização do jogo`, reunindo logos, avisos e telas exibidas logo após abrir o jogo.

## v0.25.4 — 22/08/2026

- Switches de cinematics e complementos agora sempre são liberados após uma falha e mostram o erro da operação, em vez de permanecerem bloqueados sem retorno.

## v0.25.3 — 22/08/2026

- Ao ativar uma cinematic ou um complemento de Background, versões concorrentes do mesmo BK2 são desativadas automaticamente. A escolha deixa de depender da ordem de importação dos addons.

## v0.25.2 — 22/08/2026

- Backgrounds e complementos agora removem automaticamente uma pasta extra de ZIP/RAR antes de `MoviesBink`, instalando os BK2 no destino correto. Complementos antigos são migrados e reaplicados ao abrir os detalhes do perfil-base.

## v0.25.1 — 22/08/2026

- ZIPs e RARs com muitas variações agora preservam no componente o nome da pasta original do compactado. Os arquivos de cada trio continuam juntos e somente a primeira variação chega ativada.

## v0.25.0 — 22/08/2026

- O relatório de conflitos agora diferencia sobreposições ativas resolvidas por prioridade de empates, destaca a versão preferida e resume conflitos ativos, preferências definidas e empates.
- Conflitos automáticos e marcados manualmente passaram a ser identificados no próprio relatório.

## v0.24.3 — 22/08/2026

- O scanner agora preserva mods de Background/Cinematic como `Backgrounds`, sem reinterpretar vídeos BK2 como mods de herói. A área Backgrounds permanece disponível na barra lateral antes de Generic.

## v0.24.2 — 22/08/2026

- Cinematics do mesmo arquivo agora ficam empilhadas na mesma coluna. A grade mantém três colunas e cria novas linhas quando necessário, deixando versões e complementos lado a lado de forma organizada.

## v0.24.1 — 22/08/2026

- O nome da cinematic e seu aviso de conflito agora têm espaço independente: o nome pode ser truncado sem esconder o ícone ⚠.

## v0.24.0 — 22/08/2026

- O alerta de conflitos de Cinematics agora identifica versões equivalentes por categoria, Location e nome do BK2, mesmo quando o ZIP do complemento adiciona uma pasta extra. Botões × foram centralizados.

## v0.23.9 — 22/08/2026

- Cinematics de complementos desativados agora ficam invisíveis na galeria; o complemento continua disponível na própria seção para ser reativado.

## v0.23.8 — 22/08/2026

- Cada cinematic fornecida por um complemento agora possui o botão × para removê-la individualmente, sem apagar os outros vídeos nem o complemento inteiro.

## v0.23.7 — 22/08/2026

- Complementos de Background agora podem ser removidos pelo botão × na própria linha. Ao remover um complemento ativo, as cinematics sobrepostas voltam imediatamente à camada que deve prevalecer.

## v0.23.6 — 21/08/2026

- Abertura e fechamento das abas de categorias e Locations em Cinematics agora são preservados ao alterar um switch.

## v0.23.5 — 21/08/2026

- Cada conjunto independente de cinematics em conflito agora recebe uma cor própria; todos os cards que disputam o mesmo arquivo compartilham essa cor.

## v0.23.4 — 21/08/2026

- Cinematics que usam o mesmo arquivo agora exibem o aviso ⚠ de conflito nos dois cards, com explicação no tooltip.

## v0.23.3 — 21/08/2026

- Vídeos dos complementos agora têm switch individual na galeria de Cinematics. O botão direito na linha de um complemento permite renomeá-lo, atualizando sua identificação nos vídeos.

## v0.23.2 — 21/08/2026

- As cinematics dos complementos de Background agora aparecem junto das cinematics do perfil-base, nas mesmas categorias e Locations. Cada card identifica qual complemento o fornece.

## v0.23.1 — 21/08/2026

- Cinematics agora também podem ser recolhidas pela seta no cabeçalho da seção.

## v0.23.0 — 21/08/2026

- A ativação/desativação de Background e de cada cinematic agora atualiza apenas os arquivos BK2 afetados, em vez de reconstruir todo o MoviesBink. A camada ativa com maior precedência continua sendo respeitada.
- Detalhes de mods muito grandes agora mostram inicialmente até 500 itens de conteúdo; o restante pode ser aberto sob demanda, evitando bloquear a primeira abertura.

## v0.22.3 — 21/08/2026

- Corrigidos os switches individuais da galeria de Cinematics: todos os vídeos, e não apenas o primeiro de cada grupo, agora podem ser ativados ou desativados.

## v0.22.2 — 21/08/2026

- A seção Components no detalhe agora possui uma seta para recolher e mostrar a lista sem mudar os estados dos componentes.

## v0.22.1 — 21/08/2026

- Complementos de Background agora são salvos apenas no `mods_storage` e chegam desativados, evitando sobrescritas e conflitos imediatos. Seus BK2 ficam disponíveis como prévias no detalhe antes de ativá-los.

## v0.22.0 — 21/08/2026

- Background ganhou complementos: pelo detalhe do perfil, importe outro ZIP/RAR de Background e escolha pelo switch se ele fica ativo sobre o perfil-base. A lista principal não duplica esses complementos.
- Botão e badge de Background receberam o vinho escuro solicitado.

## v0.21.4 — 21/08/2026

- As prévias agora abrem o Bink Player já maximizado, acionando o mesmo recálculo de vídeo da barra de título para corrigir o enquadramento inicial.

## v0.21.3 — 21/08/2026

- Corrigido o primeiro desenho do Bink Player aberto pelo Manager: a janela recebe automaticamente um recálculo de tamanho para evitar o vídeo cortado até usar Alt+Tab.

## v0.21.2 — 21/08/2026

- Corrigida a hierarquia de Login & Lobby: o segundo nível usa a temporada/pasta real (`Anniversary`, `Season 0`, `Season 1` etc.).
- `Entrada` passou a se chamar **Level Entrance**. O botão ▶ de cada cinematic abre seu arquivo `.bk2` no Bink Player instalado em `D:\\004. RAD Bink\\RADVideo`.

## v0.21.1 — 21/08/2026

- A galeria de cinematics agora é organizada em grupos recolhíveis por categoria e LOCATION/temporada, como `Loading → Asgard` e `Login & Lobby → Season 1`, antes dos vídeos individuais.

## v0.21.0 — 21/08/2026

- Backgrounds agora indexam cada arquivo `.bk2` como uma cinematic individual, incluindo `LoginAndLobby`, `LevelVideo`, `Loading`, `LevelEntrance` e `LevelExit`.
- A tela de detalhes ganhou uma galeria de cinematics com LOCATION/TAG, categoria, caminho e switch por arquivo. Desligar um item reconstrói o MoviesBink a partir do backup original e reaplica somente as cinematics ligadas.
- LOCATIONS identificadas passam a aparecer como skins em **Backgrounds** no filtro lateral.

## v0.20.0 — 21/08/2026

- O botão e os badges de tipo **ReShade** agora usam o vermelho `#b30c18` solicitado.
- Adicionado **Background**: importa ZIP/RAR de cinemáticas para `Marvel\\Content\\Marvel`, preserva a árvore `MoviesBink`, cria backup privado do original antes da primeira sobrescrita e oferece **Restaurar padrão** na categoria Backgrounds.

## v0.19.0 — 21/08/2026

- Adicionada a opção **ReShade** ao lado de PAK. Ela importa ZIP/RAR, mantém o compactado e as imagens na biblioteca e instala o conteúdo extraído preservando sua estrutura em `Marvel\\Binaries\\Win64`.
- Mods ReShade podem ser ativados, desativados, removidos e verificados pela integridade sem usar a pasta `~mods`.

## v0.18.2 — 21/08/2026

- Corrigida a seleção cinza ao tentar mover uma miniatura da galeria no aplicativo desktop. O arraste agora usa os eventos de mouse do WebView e impede a seleção nativa da imagem.

## v0.18.1 — 21/08/2026

- Corrigido o arraste das miniaturas no visualizador da galeria: a mídia agora acompanha o ponteiro, muda de posição visualmente durante o gesto e salva a nova ordem ao soltar.

## v0.18.0 — 19/08/2026

- As miniaturas inferiores do visualizador da galeria agora podem ser arrastadas para reorganizar as mídias do mod.
- A ordem escolhida é salva imediatamente. A primeira imagem estática da nova ordem passa a ser usada como capa do card; vídeos continuam sendo aceitos na galeria, mas não como capa.

## v0.17.0 — 19/08/2026

- Cada item de **Components** agora possui o botão **Conteúdo**, que troca a árvore de `FILE CONTENTS` para mostrar somente os arquivos daquele componente. O mesmo botão retorna à visão de todos os conteúdos.
- A leitura específica do componente só acontece quando solicitada, preservando a abertura rápida da tela de detalhes.
- **Unknown** voltou a ficar sempre visível nos filtros de tipo, inclusive quando sua contagem atual é zero.

## v0.16.0 — 19/08/2026

- A análise de tipos agora combina os assets de **todos** os contêineres `.utoc` e `.pak` pertencentes ao mod, em vez de usar somente o primeiro arquivo encontrado.
- Adicionado o tipo **Physics**. Um pacote contendo apenas assets de física deixa de ser exibido como `Unknown`; em mods híbridos, Physics aparece como tipo adicional sem substituir Mesh, Texture, Audio ou UI.
- O cache da lista de assets foi versionado para forçar uma nova leitura completa nos mods já cadastrados.
- Na seleção de **Components**, `Shift+clique` seleciona o intervalo e `Ctrl+Shift+clique` remove o intervalo, mantendo o comportamento de seleção em massa do restante do aplicativo.

## v0.15.0 — 19/08/2026

- A seção **Components** agora permite selecionar vários itens e aplicar um mesmo label em lote, além de mover o grupo selecionado para cima ou para baixo preservando a ordem entre eles.
- A **Library Health** ganhou **Ignorar mídia ausente**. A ação somente remove a pendência do diagnóstico; não apaga arquivos, ZIPs, imagens nem vídeos do `mods_storage`.

## v0.14.0 — 19/08/2026

- Perfis e ações em massa de ativar/desativar passam a guardar automaticamente um **ponto de restauração** do estado anterior.
- Adicionada a opção **Reverter última alteração em massa** na janela de Profiles. Ela restaura switches, prioridades e componentes, sem apagar arquivos ou substituir perfis salvos.

## v0.13.0 — 19/08/2026

- Adicionado backup/restauração da biblioteca em **Settings**. O backup JSON inclui catálogo, identidades, tags, componentes, capas cadastradas, perfis e configurações.
- A restauração substitui somente os registros; não apaga nem copia PAK/UCAS/UTOC, ZIPs, imagens ou vídeos do `mods_storage` e pede confirmação antes de ocorrer.

## v0.12.0 — 19/08/2026

- A verificação de integridade ganhou **reparo assistido**: para cada pendência reparável, o usuário pode restaurar backups ausentes a partir dos arquivos ativos ou reinstalar arquivos ativos ausentes a partir do backup privado.
- O reparo não sobrescreve arquivos existentes, respeita o bloqueio quando o jogo está aberto e mantém mídias faltantes e mods externos desativados como pendências manuais.

## v0.11.0 — 19/08/2026

- Adicionada a verificação de integridade da biblioteca em **Settings**. Ela diagnostica, sem alterar arquivos, backups ausentes, arquivos ativos que sumiram da pasta do jogo e mídias de galeria faltantes.
- A verificação informa quando o caminho do jogo ainda não foi configurado e registra seu resultado no histórico de atividades.

## v0.10.0 — 18/08/2026

- Adicionado **Activity History**: registra as últimas ações relevantes da biblioteca, como adicionar, mover, ativar, desativar, remover e excluir mods, inclusive alterações de componentes.
- O histórico é persistente, limitado às 100 ações mais recentes e pode ser consultado ou limpo pelo novo botão **History** no cabeçalho.

## v0.9.0 — 18/08/2026

- Perfis agora registram e restauram também a prioridade de cada mod (1–10), além de switches de mods e componentes.
- Atualizada a explicação da janela de Profiles para deixar explícito o estado que será salvo e aplicado.

## v0.8.5 — 18/08/2026

- Adicionado respiro acima da lista de cards para que a elevação e a sombra do hover não sejam cortadas pelo cabeçalho.

## v0.8.4 — 18/08/2026

- Aplicada ao tema escuro a mesma estrutura protegida do painel principal: margem entre filtros e lista, borda do painel e espaçamento interno para os cards não serem cortados na lateral.

## v0.8.3 — 18/08/2026

- Refinado o layout claro da lista: painel principal separado visualmente dos filtros, espaçamento lateral para os cards e cabeçalho branco contínuo para “All Mods” e suas ações.

## v0.8.2 — 18/08/2026

- Alinhado o grupo de prioridade (`− valor +`) com switch e botões na fileira inferior dos cards em Grid.
- Cards agora ganham elevação, sombra e borda mais visível ao passar o cursor, nos temas escuro e claro.
- No tema claro, o contraste foi movido para o fundo da área de mods, mantendo os cards claros durante o hover.

## v0.8.1 — 18/08/2026

- Corrigido o Grid com badges de tipo: o ícone do personagem fica à esquerda dos tipos e o tamanho usa o canto inferior esquerdo, sem disputar espaço com prioridade e controles.
- No tema claro, o card sob o cursor agora recebe contraste mais forte para ficar claramente identificável.

## v0.8.0 — 18/08/2026

- Removidas das configurações as opções antigas de subpastas, lista compacta e confirmação de exclusão, que não refletiam mais o fluxo atual do gerenciador.
- Adicionadas preferências persistentes para ocultar o sufixo `_9999999_P`, abrir detalhes automaticamente e exibir badges de tipo nos cards.
- Os badges de tipo passam a caber no modo Grid sem sobrepor tamanho, prioridade ou controles.
- Adicionado tema **Dark/Light** persistente; Dark continua como padrão.
- Adicionado bloqueio de operações de arquivos enquanto Marvel Rivals estiver aberto. A opção avançada permite ignorá-lo conscientemente.

## v0.7.1 — 18/08/2026

- O modo **List** ou **Grid** agora é salvo automaticamente. Ao iniciar o programa, a lista abre no mesmo modo de visualização usado por último.

## v0.7.0 — 18/08/2026

- Configurações agora oferecem cinco cores de destaque persistentes para botões, seleções e indicadores.
- A cor escolhida é pré-visualizada imediatamente; fechar a janela ou pressionar `Esc` sem salvar restaura a cor anterior.

## v0.6.2 — 18/08/2026

- `Esc` passa a fechar somente a interface que está por cima. Por exemplo: na galeria expandida fecha apenas a imagem; o próximo `Esc` fecha os detalhes do mod.

## v0.6.1 — 18/08/2026

- Ao clicar novamente na capa/ícone de um mod já selecionado, ele é removido da seleção. `Shift+clique` continua reservado para seleção por intervalo.

## v0.6.0 — 18/08/2026

- Expandida a ajuda de atalhos: `F2` renomeia o mod destacado; setas navegam pela lista; `Enter` abre detalhes após navegação por teclado; `Shift+clique` seleciona um intervalo.
- `Ctrl+E` agora alterna **todos** os mods selecionados, em vez de exigir exatamente um.
- O mod alcançado pelas setas recebe destaque visual e acompanha a rolagem da lista.
- Com uma seleção já existente, clicar na capa/ícone acima do nome de um cartão em grade adiciona o mod à seleção sem abrir detalhes.
- `Esc` fecha detalhes, visualizador de galeria, menu de contexto, perfis, ajuda, configurações e a janela de instalação.
- O visualizador da galeria agora aceita `←`/`↑` e `→`/`↓` para trocar de mídia.

## v0.5.0 — 18/08/2026

- Adicionada ajuda de **Keyboard Shortcuts** pelo botão ⌨ ou `F1`.
- Atalhos novos: `Ctrl+F` foca a busca, `Ctrl+Shift+R` atualiza a lista e `Ctrl+E` alterna o único mod selecionado.
- `Esc` agora também fecha o menu de contexto aberto.

## v0.4.0 — 18/08/2026

- Adicionado **Launch Game**: abre Marvel Rivals pelo Steam usando o protocolo do Windows, sem invocar ou exibir uma janela de CMD.

## v0.3.0 — 18/08/2026

- Adicionado o sistema de **Profiles**: salve o estado atual de todos os mods e componentes, aplique-o depois com um clique ou exclua snapshots que não usa mais.
- Aplicar um perfil não faz scan nem reclassificação: somente troca os switches necessários e reinstala os arquivos ativos correspondentes.

## v0.2.0 — 18/08/2026

- A seleção múltipla agora oferece **Marcar conflito** quando há pelo menos dois mods ativos marcados. A relação é salva manualmente no catálogo e o alerta aparece enquanto os mods envolvidos estiverem ativos.
- Alterar ou resolver um conflito não apaga mais os alertas de outros pares independentes já analisados. Os indicadores são recalculados em segundo plano após alterações.
- Corrigida a passagem do mouse entre **Assign Tag…** e o submenu de tags: o menu deixa de fechar antes do clique.

## v0.1.13 — 18/08/2026

- Após uma importação concluída, os arquivos ZIP/RAR selecionados e as imagens escolhidas para o mod são apagados da pasta de origem.
- As cópias armazenadas em `mods_storage` são preservadas: um arquivo selecionado de dentro desse armazenamento nunca é apagado.
- Arquivos `.pak`, `.ucas` e `.utoc` selecionados diretamente continuam sem remoção automática.

## v0.1.12 — 18/08/2026

- Corrigida a edição de labels dos componentes: o menu abre imediatamente, mesmo se o catálogo demorar para responder.
- Adicionado botão explícito **Label** ao lado de **Nome** em cada componente.
- O menu permanece limitado à tela, evitando abrir fora da área visível.

## v0.1.11 — 18/08/2026

- Os checkboxes dos cards agora formam uma seleção real de múltiplos mods.
- Foi adicionada uma barra contextual para ativar, desativar ou limpar a seleção em lote.
- As alterações em lote preservam o backup local de mods descobertos diretamente na pasta do jogo.

## v0.1.10 — 18/08/2026

- A tela principal agora desenha os cards antes de solicitar as capas dos mods.
- As miniaturas são carregadas em segundo plano, com no máximo três conversões simultâneas.
- Isso deixa a abertura e as recargas mais responsivas, sem mudar galerias, capas ou arquivos salvos.

## v0.1.9 — 18/08/2026

- A tela principal reutiliza em memória as miniaturas já geradas das capas dos mods.
- Recargas após trocar filtros, ativar/desativar ou alterar prioridade deixam de recodificar todas as imagens novamente.
- Miniaturas são atualizadas automaticamente quando o arquivo de imagem muda.

## v0.1.8 — 18/08/2026

- A prioridade agora é apresentada de forma consistente: **10 é a maior prioridade** e **1 é a menor**.
- O botão `+` aumenta a prioridade, o `−` diminui e a ordenação por prioridade mostra os mods mais prioritários primeiro.

## v0.1.7 — 18/08/2026

- A detecção automática passa a dar prioridade aos IDs e caminhos internos dos assets sobre nomes de arquivos, pastas e componentes.
- Isso reduz classificações erradas quando um nome cita outro personagem ou quando o pacote contém referências a outros heróis.
- A interface de **Corrigir** foi validada com pesquisa rolável de personagens e skins, mantendo a digitação manual como alternativa.

## v0.1.6 — 18/08/2026

- **Corrigir** agora abre uma interface rolável com campos editáveis e listas de personagens e skins existentes.
- É possível digitar uma skin manualmente ou escolher uma opção do catálogo antes de salvar a correção.

## v0.1.5 — 18/08/2026

- O botão **Corrigir** foi movido para o cabeçalho, ao lado do nome do mod, para ficar visível sem poluir a identificação de personagem, tipo e skin.

## v0.1.4 — 17/08/2026

- Adicionada a ação **Corrigir** na tela de detalhes para ajustar manualmente personagem e skin.
- A correção salva uma identidade manual, portanto scans futuros não voltam a classificar o mod de forma diferente.
- Mods visuais corrigidos acompanham a nova organização em `~mods` e `mods_storage`; mods somente de áudio continuam em `1_Audio`.

## v0.1.3 — 17/08/2026

- A checagem de conflitos agora ignora colisões normais entre o componente principal e seus acompanhamentos no mesmo mod.
- Um conflito interno só é mostrado quando duas ou mais opções do mesmo mod são marcadas como **Principal**.
- Entre mods separados, o alerta só é mantido quando eles pertencem ao mesmo personagem **e** à mesma skin.
- Tags e rótulos personalizados agora têm um **X** nos menus de seleção para removê-los; a remoção de uma tag também a retira dos mods que a utilizavam.
- Versão exibida atualizada para **v0.1.3**.

## v0.1.2 — 17/08/2026

- O menu de contexto não mostra mais a árvore enorme de caminhos em **Move to…**.
- **Move to…** agora abre o seletor nativo diretamente na pasta do personagem do mod.
- Ao selecionar uma pasta de skin, o Manager move o pacote para `Personagem\\Skin\\Pacote`, atualiza personagem/skin confirmados e acompanha a mudança no `mods_storage`.

## v0.1.1 — 17/08/2026

- O **Check Conflicts** agora marca cada mod envolvido com o ícone `⚠`.
- Ao clicar no aviso do card, o programa mostra quais outros mods entram em conflito e quantos assets internos eles compartilham.
- O estado dos avisos é limpo quando uma alteração pode mudar os arquivos ativos, evitando resultados antigos.
- A identificação escolhida no modal de instalação passa a ser preservada como confirmação do usuário; scans não substituem personagem/skin por uma heurística de assets mistos.
- Corrigido `ReshiramEmaMod_9999999_P` como **Emma Frost / Default**, incluindo a pasta do jogo e o backup no `mods_storage`.

## v0.1.0

- Versão inicial do Marvel Manager.
