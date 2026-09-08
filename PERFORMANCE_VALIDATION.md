# Validação de desempenho, classificações e catálogos

Data da medição: **31/08/2026**  
Escopo: auditoria somente leitura da biblioteca atual, benchmarks em cópias temporárias e validação das fontes públicas de mapping e skins. Nenhum arquivo do jogo, `mods.json`, `settings.json` ou conteúdo de `mods_storage` foi alterado. Os hashes SHA-256 dos dois JSONs reais foram comparados antes e depois do benchmark.

## Resultado principal

A demora de 20–30 segundos depois de uma importação **não foi reproduzida no caminho de atualização da home**. Com a biblioteca atual de 296 mods, 2.461 componentes e um `mods.json` de aproximadamente 6 MB:

| Operação | Resultado observado |
|---|---:|
| Montar snapshot da home | mediana 0,208 s |
| Serializar snapshot de 1.586.541 bytes | mediana 0,015 s |
| Abrir metadados de detalhes, amostra de 10 mods | mediana 0,229 s |
| Maior detalhe da amostra, 63 componentes | 0,727 s na primeira abertura temporária |
| Gerar miniatura fria de capa mediana (250.700 bytes) | 0,189 s |
| Gerar miniatura fria da maior capa (19.685.666 bytes) | 0,998 s |
| Ler miniatura já armazenada | aproximadamente 1–2 ms |
| Montar snapshot sintético de 500 mods | mediana 0,10 s |

As 281 capas cadastradas existem e as 281 revisões atuais já têm miniatura persistente. O endpoint de detalhes foi medido com `include_previews=False`, como a interface o chama, e não abriu PAK/UTOC nem decodificou a galeria.

Esses números eliminam snapshot, metadados e uma única capa como explicação isolada para 20–30 segundos. Ainda falta medir no WebView o intervalo entre `start_complete_mod_install` terminar, `reloadAll()` receber a resposta, os cards serem inseridos no DOM e a primeira capa aparecer. O benchmark do backend não inclui transporte pywebview, layout ou pintura do WebView.

## Gargalo corrigido nas classificações pendentes

Antes da correção, `list_pending_classifications()` verificava 1.382 componentes
em 12,34–15,17 s, com 42.610 chamadas a `Path.resolve()`. A implementação agora
resolve as raízes privadas/ativas uma vez por mod, continua resolvendo cada
arquivo final para recusar links/junctions e produziu o mesmo resultado funcional.
Na medição final, a operação levou **4,324 s**. O resultado atual é:

- 1.151 analisados;
- 229 pendentes de evidência atual;
- 1 com arquivo ausente;
- 1 com assets legíveis, mas tipo não reconhecido;
- 0 com falha de leitura persistida.

Essa demora pertence à tela de manutenção de classificações. `reloadAll()` não chama essa listagem, portanto ela não explica diretamente a pausa pós-importação.

## Unknown e metadados ausentes

Uma contagem bruta encontra 1.089 componentes sem tipo ou com `Unknown`, mas 1.058 são cinematics de Background (`install_target=marvel_content`) que usam metadados de localização/cinematic em vez da classificação PAK comum. Eles não devem aparecer como dívida de classificação de Mesh/Texture/Audio.

Restam 31 componentes com `Unknown` explícito:

- 18 são bancos de Background Audio (`install_target=mods`);
- 13 pertencem a mods PAK comuns.

A classificação agora usa `background_audio=True` junto de `audio_bank` como
evidência estrutural da extração confirmada de `.bnk`. Assim, os 18 bancos de
Background aparecem como `Audio` sem inferência pelo nome ou migração em massa.
Nos mods PAK comuns, somente dois continuam sem evidência: um está com arquivo
ausente e outro tem assets legíveis não reconhecidos. Esses dois permanecem
pendentes em vez de receber um tipo por palpite.

O dry-run de `reclassify_existing_components()` levou 0,24 s e encontrou 196 normalizações de metadados em 90 mods, incluindo 26 mudanças de `Unknown` explícito para tipo conhecido. Nenhuma delas foi aplicada à biblioteca real nesta auditoria. Antes de aplicar em massa, a interface deve apresentar a revisão, preservar correções manuais e manter os dois casos sem evidência como pendentes.

## Mapping 3D

O suporte local passou na validação de conteúdo de `native3d_support.get_status()` e está pronto com:

- `5.3.2-3805839+++depot_marvel+S9.5_release-Marvel.usmap`;
- build 3.805.839;
- Git blob SHA-1 `618485536596af9853043649976a57d3ee42d564`;
- SHA-256 local `1ace3489d8284eb294438cb389bdb3741fac5662e0cc10c866d57ef2b3ca30f5`.

A consulta ao índice atual do [SpaceDepot/rivals-depot](https://github.com/SpaceDepot/rivals-depot/tree/main/usmap) retornou exatamente o mesmo nome, build, tamanho e Git blob SHA-1. Não há atualização de mapping pendente. O fluxo atual também rejeita downgrade, valida o Git blob anunciado, limita tamanho e preserva o cache anterior quando uma atualização falha.

## Catálogo de skins

O catálogo local usado pelo app (`backend/rivalskins_data.json`) foi atualizado e está estruturalmente íntegro:

- 691 entradas: 572 IDs numéricos e 119 recolors `ps`;
- nenhum ID malformado;
- nenhum nome, personagem, URL ou ícone ausente;
- todos os 572 costumes numéricos resolvem para o mesmo personagem jogável indicado pelo slug;
- não há colisão entre IDs numéricos e IDs de recolor;
- o dump legado tem dois IDs repetidos, mas ambos permanecem dentro do mesmo personagem e a precedência existente é determinística.

O catálogo gerado consultado do [Rivalskins](https://rivalskins.com/?type=costume) contém 690 costumes. A cópia local preserva também um recolor válido que não aparece no arquivo gerado (`ps1040502`) e recebeu os seis costumes novos:

| ID | Personagem | Skin |
|---|---|---|
| 1032308 | Squirrel Girl | Acorn Divinity |
| 1042307 | Peni Parker | Liquid Shell |
| 1054504 | Phoenix | Viridian Vogue |
| 1055503 | Daredevil | Attorney at Law |
| 1056503 | Angela | Queen of Hel |
| 1063300 | Cyclops | Elegant Eye |

Todos os seis prefixos já tinham mapeamento local de personagem; a atualização
foi revisada e o updater de mesclagem preservou o recolor local ainda válido.

Há também um `rivalskins_data.json` na raiz com 632 entradas. Ele não é lido pelo app nem empacotado; está 53 entradas atrás do arquivo de `backend/` e todos os registros compartilhados divergem em algum campo. Remover esse arquivo antigo ou marcá-lo explicitamente como fonte histórica evita atualizar a cópia errada.

## Regressões adicionadas e comandos

Foi adicionado `tests/test_catalog_integrity.py`, cobrindo esquema, IDs duplicados, resolução personagem/skin, colisões de recolor, URLs, ícones e filtragem de Costume no parser do catálogo gerado.

O benchmark reproduzível está em `tests/benchmark_performance_validation.py`:

```powershell
python tests/benchmark_performance_validation.py
python tests/benchmark_performance_validation.py --local-read-only --repeats 3
python tests/benchmark_performance_validation.py --local-read-only --repeats 3 --profile-classifications
```

Validação executada:

- suíte Python completa: 336 testes executados, 335 aprovados e 1 ignorado pela restrição conhecida de symlink real no Windows;
- 7 dos testes aprovados são as novas regressões de integridade de catálogo;
- os nove arquivos de testes JavaScript passaram; os dois que usam `vm.SourceTextModule` foram executados com `node --experimental-vm-modules`, exigido pelo Node 18 disponível;
- compilação dos dois novos arquivos Python aprovada.

O catálogo foi atualizado e a alternância reversível de uma variante aninhada foi
testada nos arquivos ativos. O jogo iniciou, mas a aparência dentro da janela
protegida do Marvel Rivals, a instalação física em outro PC e o tempo completo do
WebView após uma importação real ainda exigem validação separada.
