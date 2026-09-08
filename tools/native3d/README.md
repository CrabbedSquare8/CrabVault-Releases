# Prévia 3D nativa

O botão 3D lê somente os containers do componente escolhido. Os pacotes globais
do jogo são dependências lidas diretamente na origem, mesmo em outro disco,
nunca fontes para uma varredura completa. Não há cópia nem hardlink de containers. Não é necessário ativar o componente nem modificar o catálogo.

## Pipeline

1. O provider do CUE4Parse identifica os meshes do componente.
2. Apenas a variante solicitada é serializada em GLB. `PreviewMeshWriter` grava
   o LOD indexado diretamente, com posições, normais, tangentes e todos os UVs
   existentes. Não há decimação nem reconstrução de rig; a prévia é estática,
   na pose de referência.
3. `PreviewTextures` normaliza os caminhos e prepara cada textura uma vez.
   As variantes compartilham o mesmo cache e as mesmas imagens na interface.
4. `OriginalTextureWriter` entrega os blocos BC1/2/3/7 originais no formato local
   MMTX apenas quando a GPU informa suporte. Normal maps e formatos não
   compatíveis usam o decoder gerenciado AssetRipper e PNG lossless, sem Detex externo. Texturas sem mipmaps
   completos recebem níveis filtrados na GPU, sem compressão adicional.
5. O manifest registra as variantes prontas e pendentes. Mudanças nos containers,
   mapping, bibliotecas ou extrator invalidam o cache. Resultados incompletos não
   são apresentados como sucesso. Esc encerra somente o processo daquele pedido.

Cache: `frontend/viewer-cache/<mod>/<componente>/`. Temporários:
`.cache/native3d/`. Ambos permanecem na pasta do Manager. As listas temporárias
indicam os arquivos de origem, abertos somente para leitura pelo extrator.

## Compilar

Com as dependências já restauradas localmente, em PowerShell na raiz do projeto:

```powershell
$env:DOTNET_CLI_HOME = Join-Path (Get-Location) '.dotnet-home'
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'
.\.dotnet-sdk-10\dotnet.exe build tools\native3d\Marvel3DExtractor.csproj -c Release --no-restore
.\.dotnet-sdk-10\dotnet.exe publish tools\native3d\Marvel3DExtractor.csproj -c Release -r win-x64 --self-contained true --no-restore -o tools\native3d\runtime
```

O Manager prefere o executável publicado com .NET incluído. O SDK é necessário
somente para desenvolver/compilar; não faz parte do pacote entregue ao usuário.
O fallback DLL + SDK só existe para desenvolvimento quando o executável não está
presente. `check_runtime.py` rejeita uma publicação que exija .NET externo.

## Suporte independente

O Manager não consulta `fmodel_path`, não abre FModel e não depende de seus
arquivos. Na primeira prévia, `backend/native3d_support.py` prepara os codecs e
o mapping em `.cache/native3d/support`, usando HTTPS, hashes e gravação atômica.
As próximas aberturas usam o suporte verificado localmente, sem conexão. Em
Configurações, “Preparar / atualizar suporte 3D” consulta uma nova versão do
mapping, sem descartar a cópia anterior quando o download falha ou é cancelado.
Uma atualização do jogo pode exigir novo mapping e/ou atualização do leitor.

Consulte [SUPPORT.md](SUPPORT.md) para fontes, verificação e termos dos codecs.
Esse cache não é redistribuído no pacote portátil. Uma pasta de jogo válida
continua necessária para resolver materiais e dependências dos modelos.

## Verificar

```powershell
python -B -m unittest discover -s tests -v
node --experimental-vm-modules tests\test_native_textures.mjs
node --experimental-vm-modules tests\test_model_viewer_controls.mjs
python tools\native3d\check_runtime.py
python tools\native3d\smoke_independent_preview.py ID_DO_MOD ID_DO_COMPONENTE --gpu
python tools\native3d\benchmark_preview.py ID_DO_MOD ID_DO_COMPONENTE --gpu
python tools\native3d\preview_smoke_server.py --port 8766
```

O benchmark sempre cria um cache vazio separado e não grava mods/settings. O
teste visual em `http://127.0.0.1:8766/__preview_test` usa a interface real com
uma API limitada à preparação/cancelamento; não substitui a API do aplicativo.
`--baseline-root` permite comparar um diretório exportado antes da mudança.
Remover somente os diretórios `benchmark-*`/`qa-*` criados pelo teste ao terminar,
nunca o cache do usuário ou os arquivos originais.

`compare_preview_geometry.py antes.glb depois.glb` compara triângulos, posições e
UVs, ignorando apenas canais vazios adicionais do exportador antigo. Na validação
do Peni, os 191.784 triângulos e seus UVs foram preservados; no SuperBuu, 39.470.

### Medições locais — 30/08/2026

Cada primeira abertura usou um cache de prévia vazio e separado. O novo fluxo
prepara somente a variante selecionada; as outras continuam disponíveis sob
demanda. A última coluna inclui o upload das texturas e a exibição na interface.

| Componente | Preparação anterior | Preparação nova | Clique até aparecer |
| --- | ---: | ---: | ---: |
| SuperBuu | >120 s (timeout) | 3,418 s | 4,69 s |
| Zi_PeniPDef_B1 | 106,775 s | 3,496 s | 4,31 s |
| LopunnyRogueMega | 9,406 s | 1,804 s | 2,27 s |

Esses valores não são uma garantia para todos os mods, GPUs ou estados do disco.
Validação: 16 testes Python e 12 verificações JavaScript, comparação de geometria
com o exportador anterior e abertura dos três exemplos na interface real.

Materiais específicos do jogo continuam sendo aproximações do shader original;
otimizar a prévia não significa reproduzir todo o renderer do Marvel Rivals.

### Independência — 31/08/2026 (v0.31.0)

Publicação self-contained win-x64 com .NET 10.0.11. Smoke com `fmodel_path`
removido, `PATH` vazio e `DOTNET_ROOT` isolado: Lopunny abriu em 5,404 s usando
PNG e 1,492 s com texturas de GPU, sem falhas de leitura (16 pacotes, dois
modelos identificados). Os caches do teste foram excluídos ao terminar. Estes
são tempos de conversão locais, não uma garantia de tempo de desenho ou prova
de funcionamento em todo computador limpo. Nenhum arquivo do jogo foi alterado.
