# Arquivos de suporte do visualizador 3D

O Manager não abre FModel, não lê suas configurações e não copia arquivos de sua instalação. O extrator e o visualizador pertencem ao Manager; os codecs e os dados de interpretação descritos abaixo continuam sendo componentes de terceiros, com suas respectivas licenças e fontes.

## Primeiro uso, atualização e funcionamento sem rede

- Na primeira abertura 3D, o Manager verifica a Oodle incluída e prepara os arquivos necessários em `.cache/native3d/support/`. O mapping e o zlib ainda exigem acesso HTTPS ao GitHub nessa preparação; não é necessário instalar FModel, Unreal Editor ou configurar caminhos desses programas.
- A ação **Preparar/atualizar suporte 3D** também prepara o suporte e consulta o mapping mais recente. As versões dos codecs são fixas: mudanças de versão e hashes exigem atualização do código do Manager.
- Com o suporte válido já preparado, abrir um modelo não faz novas consultas de rede. O Manager verifica os arquivos locais e os reutiliza.
- Uma atualização que falha não substitui o conjunto anterior. Downloads interrompidos não se tornam o conjunto ativo; uma nova tentativa pode reutilizar os codecs já verificados.
- O status nas configurações é uma consulta local. Não significa que o mapping instalado corresponda a uma atualização do jogo que acabou de sair.
- O jogo instalado e os pacotes do mod continuam sendo necessários para as respectivas dependências do modelo. Não há download de modelos, texturas ou arquivos originais do jogo por esse mecanismo.

## Fontes

### Mapping USMAP

[SpaceDepot/rivals-depot](https://github.com/SpaceDepot/rivals-depot) é uma fonte da comunidade de Marvel Rivals, não um serviço oficial da NetEase/Marvel. O Manager consulta os arquivos públicos da pasta `usmap` e seleciona o maior número de build cujo nome corresponde a um lançamento `S…_release-Marvel.usmap`; arquivos de preview/PY e de outros jogos são excluídos.

O tamanho e o SHA-1 do objeto Git informados pela API do GitHub precisam corresponder ao download. O Manager também verifica o cabeçalho USMAP, limita o tamanho descomprimido declarado e registra um SHA-256 local. Essa validação detecta corrupção ou troca entre a listagem e o download; não transforma dados da comunidade em dados oficiais nem comprova compatibilidade com toda versão do jogo.

Endpoint: `https://api.github.com/repos/SpaceDepot/rivals-depot/contents/usmap?ref=main`.

### Oodle

O Manager inclui `oo2core_9_win64.dll` **Oodle 2.9.10**, obtida da pasta `win/redist` do SDK em [WorkingRobot/OodleUE](https://github.com/WorkingRobot/OodleUE), no commit fixado `5e38cb6c99c588b51cde0cae4a6420d6bc865605`. A DLL é verificada antes de ser copiada para o cache atômico usado pelo [OodleHelper do CUE4Parse](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/Compression/OodleHelper.cs).

**Oodle não é tratado como uma biblioteca de código aberto.** OodleUE é um projeto da comunidade; não é o site oficial da Epic/RAD. Seu [aviso sobre a EULA](https://github.com/WorkingRobot/OodleUE#eula-notice) remete aos [termos da Unreal Engine](https://www.unrealengine.com/eula/unreal) e declara que os arquivos não pertencem ao mantenedor do repositório.

A DLL acompanha o Manager em `tools/native3d/oodle/`, junto de `NOTICE.txt`; o cache privado não entra no ZIP. Este documento identifica origem e avisos do fornecedor e não substitui os termos aplicáveis. A compatibilidade foi validada com containers atuais do Marvel Rivals nos caminhos PNG e GPU antes da substituição da 2.9.16.

### Zlib-ng

O arquivo `zlib-ng2.dll.gz` vem da versão **1.0.0** do [Zlib-ng.NET](https://github.com/NotOfficer/Zlib-ng.NET/releases/tag/1.0.0), origem usada pelo [ZlibHelper do CUE4Parse](https://github.com/FabianFG/CUE4Parse/blob/master/CUE4Parse/Compression/ZlibHelper.cs). O wrapper .NET informa licença MIT; a biblioteca nativa tem os [termos do zlib-ng](https://github.com/zlib-ng/zlib-ng/blob/develop/LICENSE.md). Os respectivos autores mantêm os direitos sobre esses componentes.

## Integridade e limites

Os downloads só aceitam as origens HTTPS definidas no código. Redirecionamentos de releases são limitados ao CDN de assets do GitHub. A Oodle não é baixada: seu arquivo interno passa pelas mesmas validações de tamanho, SHA-256, PE e arquitetura x64 antes de ser ativado. Limites de bytes, tempo e cancelamento protegem a preparação.

Os SHA-256 dos downloads foram conferidos com as fontes registradas; os das DLLs foram calculados sem executar seus arquivos. Valores fixados em `backend/native3d_support.py`:

| Arquivo | SHA-256 |
|---|---|
| Oodle DLL 2.9.10 | `6f5d41a7892ea6b2db420f2458dad2f84a63901c9a93ce9497337b16c195f457` |
| Zlib GZIP | `e11f814f64821c482fb81c05fb20d9e5a3be0feb0e2f8fd9480d1f341163e2c1` |
| Zlib DLL | `454be2f3d10f804ace577198401431db5e95d0286b59589bc28a40085388e7c2` |

Além dos hashes, DLLs precisam apresentar cabeçalho PE Windows x64. Symlinks/junctions nos caminhos de suporte são recusados. Arquivos são publicados por substituição atômica, com nomes derivados do conteúdo; `current.json` só passa a apontar para um conjunto completo depois que todos os arquivos foram verificados. Consultas simultâneas são coordenadas entre threads e processos. Atualizar para o mesmo conteúdo preserva o mtime dos arquivos para não invalidar prévias sem necessidade.
