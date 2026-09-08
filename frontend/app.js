// =========================================================
// CrabVault — app.js
// =========================================================

const state = {
  mods: [],
  characters: [],
  types: [],
  tags: [],
  folders: [],
  settings: {},
  roster: [],
  activeCharacter: null,
  activeSkin: null,
  characterSkins: [],
  activeTypes: new Set(),
  activeTags: new Set(),
  search: "",
  sort: "name-asc",
  ctxMod: null,
  // estado temporário do modal Add Mod
  pickedCharacter: null,
  pickedSkin: "",
  installKind: "pak",
  installParentBackgroundId: null,
  installSourceFolder: "",
  installFolderChosenManually: false,
  detailsModId: null,
  cinematicPreviewIndex: 0,
  detailContentsExpanded: false,
  componentOrderEditing: false,
  collapsedComponentSections: new Set(),
  collapsedCinematicSections: new Set(),
  cinematicSectionStates: new Map(),
  selectedComponentIds: new Set(),
  lastSelectedComponentId: null,
  componentKindFilters: new Map(),
  activeComponentContentId: null,
  componentContent: null,
  view: "list",
  // Mantém o último relatório, mas só exibe os responsáveis ainda ativos.
  conflictsByMod: new Map(),
  conflictRecords: [],
  conflictCheckPerformed: false,
  conflictRevision: 0,
  conflictRequestSerial: 0,
  conflictRefreshPending: false,
  conflictShowResultsPending: false,
  conflictManualCheckInProgress: false,
  conflictRefreshTimer: null,
  conflictRefreshInProgress: false,
  thumbnailPending: new Set(),
  thumbnailQueue: [],
  thumbnailWorkers: 0,
  selectedModIds: new Set(),
  lastSelectedModId: null,
  focusedModId: null,
  keyboardNavigation: false,
};

const THUMBNAIL_WORKER_LIMIT = 3;
const DEFAULT_ACCENT = "#e0333f";
const DEFAULT_THEME = "dark";
const DEFAULT_LANGUAGE = "pt-BR";

const TUTORIAL_COPY = {
  "pt-BR": {
    kicker: "TOUR PELA INTERFACE", back: "Voltar", next: "Próximo", review: "Recomeçar", done: "Entendi", counter: (current, total) => `${current} de ${total}`,
    chapters: [
      { id: "setup", icon: "⚙", label: "Início" },
      { id: "install", icon: "＋", label: "Instalar PAK" },
      { id: "details", icon: "◉", label: "Mod e detalhes" },
      { id: "scan", icon: "⌕", label: "Scan" },
      { id: "safety", icon: "✓", label: "Organizar" },
    ],
    steps: [
      { chapter: "setup", icon: "📁", target: "#btn-settings", placement: "left", focus: "Configurações", title: "Configure a pasta do jogo", description: "Este é o botão de Configurações. Nele, o Manager pode detectar automaticamente onde o Marvel Rivals lê os mods ou você pode escolher a pasta.", points: ["A pasta ativa do jogo e mods_storage são lugares diferentes.", "mods_storage é a biblioteca privada; a pasta ~mods contém apenas o que está ativo."] },
      { chapter: "setup", icon: "⚙", media: "assets/tutorial/settings-overview.png", mediaClass: "settings", mediaAlt: "Configurações de pasta do jogo, suporte 3D, exibição e idioma", mediaCaption: "As Configurações reúnem os recursos gerais do Manager e permitem rever este tutorial.", title: "Conheça as Configurações", description: "Além da pasta do jogo, esta tela controla o suporte 3D, a apresentação dos mods e o idioma da interface.", points: ["Preparar / atualizar suporte 3D baixa e verifica os arquivos de leitura necessários; a pasta do jogo continua obrigatória.", "Exibição do mod controla sufixo, abertura dos detalhes e badges mostrados nos cards.", "Idioma altera toda a interface, e Rever tutorial reinicia este guia quando quiser."] },
      { chapter: "install", icon: "＋", target: "#btn-add-mod", placement: "bottom", focus: "Botão PAK", title: "Comece pelo botão PAK", description: "Use PAK para instalar mods em ZIP, RAR ou 7z e também pacotes Unreal soltos. ReShade e Background têm botões próprios porque usam outros destinos.", points: ["A seleção de arquivos acontece primeiro; nada é instalado só por abrir esse botão.", "Na tela seguinte você revisa nome, detecção, tags e imagens."] },
      { chapter: "install", icon: "①", media: "assets/tutorial/pak-file-selection.png", mediaClass: "wide", mediaAlt: "Exemplo da seleção de um ZIP e de um trio PAK, UCAS e UTOC", mediaCaption: "Exemplo: um arquivo compactado e um trio de arquivos Unreal selecionáveis na mesma janela.", mediaFocus: { x: 3, y: 11, width: 82, height: 14, label: "ZIP ou trio PAK + UCAS + UTOC" }, title: "Escolha o ZIP ou o pacote Unreal", description: "Na janela do Windows, selecione o compactado do mod ou os arquivos que formam o pacote Unreal.", points: ["Um pacote moderno normalmente usa três arquivos com o mesmo nome: .pak, .ucas e .utoc; selecione o trio inteiro.", "PAK legado solto também é aceito quando esse é o formato original do mod.", "Você pode selecionar vários ZIPs ou vários pacotes de uma vez; eles entram como componentes — variações ou complementos — de um único mod."] },
      { chapter: "install", icon: "②", media: "assets/tutorial/pak-install-form.png", mediaClass: "wide", mediaAlt: "Exemplo do formulário de instalação depois da análise dos arquivos", mediaCaption: "O Manager analisa os arquivos antes da instalação e mostra o resultado para revisão.", title: "Revise o mod antes de instalar", description: "Depois da seleção, o Manager propõe um nome e mostra personagem e tipos detectados. O nome personalizado é opcional.", points: ["Cada ZIP ou pacote selecionado é preservado como componente do mesmo registro.", "Mesh, Texture, Physics, UI e Audio podem aparecer juntos; os tipos são cumulativos.", "Instalar mod é a confirmação que inicia a cópia para a biblioteca e para a pasta ativa."] },
      { chapter: "install", icon: "③", media: "assets/tutorial/pak-tags.png", mediaClass: "portrait", mediaAlt: "Exemplo do menu de tags durante a instalação", mediaCaption: "Tags existentes podem ser combinadas, e + Nova tag cria outra sem sair da importação.", mediaFocus: { x: 47, y: 22, width: 52, height: 76, label: "Menu de tags" }, title: "Organize com tags", description: "O botão + abre as tags já cadastradas e permite criar outra. Você pode aplicar mais de uma ao mesmo mod.", points: ["Tags servem para busca e organização no Manager; elas não mudam os arquivos do jogo.", "Exemplos úteis são NSFW, SFW, Broken, autor, versão ou qualquer categoria pessoal.", "As tags também podem ser adicionadas e removidas depois."] },
      { chapter: "install", icon: "④", media: "assets/tutorial/pak-images.png", mediaClass: "wide", mediaAlt: "Exemplo de várias imagens selecionadas para a galeria do mod", mediaCaption: "Use Ctrl ou Shift para selecionar várias imagens de uma vez.", mediaFocus: { x: 3, y: 15, width: 49, height: 23, label: "Várias imagens selecionadas" }, title: "Adicione capa e galeria", description: "O botão azul permite selecionar uma ou várias imagens na mesma janela.", points: ["A primeira imagem estática disponível vira a capa do card.", "As demais aparecem na galeria dos detalhes; vídeos também podem ser adicionados depois.", "Capa, ordem e itens da galeria continuam editáveis após a instalação."] },
      { chapter: "install", icon: "⑤", media: "assets/tutorial/pak-installed-result.png", mediaClass: "wide", mediaAlt: "Exemplo do mod instalado aparecendo na biblioteca", mediaCaption: "Resultado: o novo mod aparece como card na biblioteca, pronto para ser ativado e aberto.", mediaFocus: { x: 15, y: 12, width: 14, height: 34, label: "Mod instalado" }, title: "O mod agora está na biblioteca", description: "Quando a operação termina, o card mostra capa, nome, personagem, tipos, tamanho e switch.", points: ["O switch controla se os componentes escolhidos estão ativos no jogo.", "A preservação do ZIP e a exclusão dos arquivos originais seguem as preferências das Configurações.", "Clique no card para abrir todos os detalhes."] },
      { chapter: "details", icon: "▣", media: "assets/tutorial/example-mod-card.png", mediaClass: "portrait", mediaAlt: "Card de exemplo para uma biblioteca inicialmente vazia", mediaCaption: "Este card é apenas uma demonstração do que aparecerá depois de instalar ou escanear um mod.", title: "Como ler um card de mod", description: "Mesmo que a biblioteca esteja vazia, este exemplo mostra a aparência de um mod cadastrado.", points: ["A capa e o nome identificam o mod; os badges mostram personagem e todos os tipos detectados.", "O switch ativa ou desativa o mod e ✕ abre a remoção.", "A caixa no canto seleciona o card para ações em massa."] },
      { chapter: "details", icon: "▤", media: "assets/tutorial/example-mod-details.png", mediaClass: "wide", mediaAlt: "Página de detalhes de um mod com identidade, galeria, tags e componentes", mediaCaption: "A página de detalhes reúne tudo que pertence ao mesmo mod.", mediaFocus: { x: 17, y: 5, width: 68, height: 61, label: "Identidade, galeria e tags" }, title: "Identidade, galeria e tags", description: "No topo ficam nome, personagem, tipos e skin. Corrigir ajusta a identidade manualmente sem o próximo scan desfazer a escolha.", points: ["Galeria reúne capa, imagens e vídeos; + Mídia adiciona novos itens.", "Tags podem ser criadas ou aplicadas pelo + dessa seção.", "O nome do mod e o link de origem ficam disponíveis mais abaixo nos detalhes."] },
      { chapter: "details", icon: "☷", media: "assets/tutorial/example-mod-details.png", mediaClass: "wide", mediaAlt: "Página de detalhes destacando a lista de componentes", mediaCaption: "Variações e complementos permanecem dentro do mesmo mod e podem ser controlados separadamente.", mediaFocus: { x: 20, y: 65, width: 60, height: 33, label: "Lista" }, title: "Variações e complementos", description: "Componentes separa os pacotes que pertencem ao mod. As abas Todos, Variações e Complementos filtram a lista sem mudar os arquivos.", points: ["O switch de cada linha escolhe o componente ativo; relações podem impedir combinações incompatíveis.", "+ adiciona uma variante lançada depois, e arrastar PAK/UCAS/UTOC/ZIP/RAR/7z faz o mesmo.", "3D abre a prévia Mesh, Conteúdo lista os arquivos e ⋯ reúne nome, rótulo, diagnóstico, relações e gerenciamento."] },
      { chapter: "scan", icon: "⌕", target: "#btn-scan-mods", placement: "bottom", focus: "Buscar mods instalados", title: "Transforme os arquivos de ~mods em cards", description: "Buscar mods instalados encontra os pacotes que já foram colocados manualmente na pasta ~mods e cria os cards correspondentes no Manager.", points: ["Arquivos .pak, .ucas e .utoc do mesmo pacote são agrupados no mesmo card.", "O scan não baixa nem instala arquivos da internet; para um mod novo em ZIP/RAR/7z, use o botão PAK."] },
      { chapter: "safety", icon: "⌕", target: ".toolbar", placement: "bottom", focus: "Busca e organização", title: "Encontre e organize", description: "A barra pesquisa a biblioteca e reúne ordenação e tags. Personagem, tipo e pasta ficam na coluna à esquerda.", points: ["Profiles salva combinações de mods e componentes ativos.", "History mostra alterações recentes e ajuda a entender o que mudou."] },
      { chapter: "safety", icon: "⚠", target: "#btn-conflicts", placement: "bottom", focus: "Verificar conflitos", title: "Evite incompatibilidades", description: "Este botão procura mods ativos que alteram os mesmos assets e mostra os concorrentes encontrados.", points: ["Você pode desativar o concorrente pelo próprio alerta.", "Por segurança, alterações no jogo são bloqueadas enquanto Marvel Rivals está aberto."] },
      { chapter: "safety", icon: "▣", media: "assets/tutorial/settings-import-maintenance.png", mediaClass: "settings", mediaAlt: "Configurações de arquivos importados, bloqueio do jogo e manutenção da biblioteca", mediaCaption: "Essas opções definem o que será preservado e quais verificações serão executadas na biblioteca.", title: "Arquivos e manutenção", description: "As duas opções de importação são independentes: uma guarda uma cópia extra do compactado e a outra decide se as origens externas serão apagadas depois do sucesso.", points: ["A cópia instalável em mods_storage continua existindo mesmo sem o backup extra do ZIP/RAR/7z.", "Ignorar o bloqueio permite alterações com o jogo aberto; desmarcado, o Manager bloqueia essas operações por segurança.", "Integridade, classificações pendentes e operações interrompidas só alteram algo depois da sua revisão."] },
      { chapter: "safety", icon: "✓", media: "assets/tutorial/settings-backups-appearance.png", mediaClass: "settings", mediaAlt: "Configurações de backup do catálogo, backup completo e aparência", mediaCaption: "O botão Salvar aplica as preferências; as ações de backup abrem seus próprios fluxos de revisão.", title: "Backups e aparência", description: "Backup do catálogo guarda cadastro, tags, capas, componentes, perfis e configurações. Backup completo inclui também os arquivos dos mods, mídias e correções pessoais.", points: ["Extrair backup completo cria outra pasta e não substitui nem ativa automaticamente a biblioteca atual.", "Tema escuro, tema claro e cor de destaque mudam somente a aparência.", "Salvar confirma as preferências feitas nesta tela."] },
    ],
  },
  en: {
    kicker: "INTERFACE TOUR", back: "Back", next: "Next", review: "Start over", done: "I understand", counter: (current, total) => `${current} of ${total}`,
    chapters: [
      { id: "setup", icon: "⚙", label: "Start" },
      { id: "install", icon: "＋", label: "Install PAK" },
      { id: "details", icon: "◉", label: "Mod details" },
      { id: "scan", icon: "⌕", label: "Scan" },
      { id: "safety", icon: "✓", label: "Organize" },
    ],
    steps: [
      { chapter: "setup", icon: "📁", target: "#btn-settings", placement: "left", focus: "Settings", title: "Set the game folder", description: "This is the Settings button. The Manager can automatically detect where Marvel Rivals loads mods, or you can choose the folder yourself.", points: ["The active game folder and mods_storage are different locations.", "mods_storage is your private library; ~mods contains only active files."] },
      { chapter: "setup", icon: "⚙", media: "assets/tutorial/settings-overview.png", mediaClass: "settings", mediaAlt: "Settings for the game folder, 3D support, mod display, and language", mediaCaption: "Settings contains the Manager's general options and lets you review this tutorial.", title: "Understand Settings", description: "Besides the game folder, this screen controls 3D support, how mods are presented, and the interface language.", points: ["Prepare / update 3D support downloads and verifies the required reading files; the game folder is still required.", "Mod display controls suffixes, automatic Details opening, and type badges on cards.", "Language changes the entire interface, and Review tutorial restarts this guide whenever needed."] },
      { chapter: "install", icon: "＋", target: "#btn-add-mod", placement: "bottom", focus: "PAK button", title: "Start with the PAK button", description: "Use PAK for ZIP, RAR, or 7z archives and loose Unreal packages. ReShade and Background have separate buttons because they use different destinations.", points: ["File selection happens first; opening this button does not install anything by itself.", "The next screen lets you review the name, detection, tags, and images."] },
      { chapter: "install", icon: "①", media: "assets/tutorial/pak-file-selection.png", mediaClass: "wide", mediaAlt: "Example selecting a ZIP and a PAK, UCAS, and UTOC trio", mediaCaption: "Example: an archive and an Unreal package trio selectable from the same window.", mediaFocus: { x: 3, y: 11, width: 82, height: 14, label: "ZIP or PAK + UCAS + UTOC trio" }, title: "Choose the ZIP or Unreal package", description: "In the Windows dialog, select the mod archive or every file that belongs to the Unreal package.", points: ["A modern package normally has three files with the same name: .pak, .ucas, and .utoc; select the complete trio.", "A loose legacy PAK is also accepted when that is the mod's original format.", "You can select multiple ZIPs or multiple packages at once; they become variations or add-ons inside one mod."] },
      { chapter: "install", icon: "②", media: "assets/tutorial/pak-install-form.png", mediaClass: "wide", mediaAlt: "Example installation form after file analysis", mediaCaption: "The Manager analyzes files before installation and presents the result for review.", title: "Review the mod before installing", description: "After selection, the Manager suggests a name and displays the detected character and types. A custom name is optional.", points: ["Each selected ZIP or package is preserved as a component of the same entry.", "Mesh, Texture, Physics, UI, and Audio can appear together; types are cumulative.", "Install mod is the confirmation that starts copying to the library and active folder."] },
      { chapter: "install", icon: "③", media: "assets/tutorial/pak-tags.png", mediaClass: "portrait", mediaAlt: "Example tags menu during installation", mediaCaption: "Existing tags can be combined, and + New tag creates another without leaving the import.", mediaFocus: { x: 47, y: 22, width: 52, height: 76, label: "Tags menu" }, title: "Organize with tags", description: "The + button opens existing tags and lets you create another. A mod can have more than one tag.", points: ["Tags are used for searching and organizing in the Manager; they do not change game files.", "Useful examples include NSFW, SFW, Broken, author, version, or any personal category.", "Tags can also be added or removed later."] },
      { chapter: "install", icon: "④", media: "assets/tutorial/pak-images.png", mediaClass: "wide", mediaAlt: "Example selecting multiple images for a mod gallery", mediaCaption: "Use Ctrl or Shift to select multiple images at once.", mediaFocus: { x: 3, y: 15, width: 49, height: 23, label: "Multiple images selected" }, title: "Add a cover and gallery", description: "The blue button lets you select one or several images in the same dialog.", points: ["The first available static image becomes the card cover.", "The others appear in Details; videos can also be added later.", "The cover, order, and gallery items remain editable after installation."] },
      { chapter: "install", icon: "⑤", media: "assets/tutorial/pak-installed-result.png", mediaClass: "wide", mediaAlt: "Example of an installed mod in the library", mediaCaption: "Result: the new mod appears as a library card, ready to be enabled and opened.", mediaFocus: { x: 15, y: 12, width: 14, height: 34, label: "Installed mod" }, title: "The mod is now in your library", description: "After the operation finishes, the card shows its cover, name, character, types, size, and switch.", points: ["The switch controls whether the selected components are active in the game.", "Archive preservation and source-file deletion follow your Settings preferences.", "Click the card to open all details."] },
      { chapter: "details", icon: "▣", media: "assets/tutorial/example-mod-card.png", mediaClass: "portrait", mediaAlt: "Example card for an initially empty library", mediaCaption: "This card is only a demonstration of what appears after installing or scanning a mod.", title: "How to read a mod card", description: "Even when your library is empty, this example shows what a registered mod looks like.", points: ["The cover and name identify the mod; badges show its character and every detected type.", "The switch enables or disables the mod, and ✕ opens removal.", "The corner checkbox selects the card for bulk actions."] },
      { chapter: "details", icon: "▤", media: "assets/tutorial/example-mod-details.png", mediaClass: "wide", mediaAlt: "Mod details page with identity, gallery, tags, and components", mediaCaption: "The Details page keeps everything that belongs to the same mod together.", mediaFocus: { x: 17, y: 5, width: 68, height: 61, label: "Identity, gallery, and tags" }, title: "Identity, gallery, and tags", description: "The top area shows name, character, types, and skin. Correct changes identity manually without a later scan undoing it.", points: ["Gallery contains the cover, images, and videos; + Media adds new items.", "Tags can be created or applied from the + in this section.", "The mod name and source link are available farther down in Details."] },
      { chapter: "details", icon: "☷", media: "assets/tutorial/example-mod-details.png", mediaClass: "wide", mediaAlt: "Mod details page highlighting the components list", mediaCaption: "Variations and add-ons stay inside one mod and can be controlled separately.", mediaFocus: { x: 20, y: 65, width: 60, height: 33, label: "List" }, title: "Variations and add-ons", description: "Components separates packages that belong to the mod. All, Variations, and Add-ons filter the list without changing files.", points: ["Each row switch chooses an active component; relationships can block incompatible combinations.", "+ adds a variant released later, and dragging PAK/UCAS/UTOC/ZIP/RAR/7z does the same.", "3D opens the Mesh preview, Contents lists files, and ⋯ contains name, label, diagnostics, relationships, and management."] },
      { chapter: "scan", icon: "⌕", target: "#btn-scan-mods", placement: "bottom", focus: "Scan installed mods", title: "Turn the files in ~mods into cards", description: "Scan installed mods finds packages already placed manually in ~mods and creates their corresponding cards in the Manager.", points: ["Files with .pak, .ucas, and .utoc from the same package are grouped into one card.", "Scan does not download or install files from the internet; use PAK for a new ZIP/RAR/7z mod."] },
      { chapter: "safety", icon: "⌕", target: ".toolbar", placement: "bottom", focus: "Search and organization", title: "Find and organize", description: "The bar searches the library and contains sorting and tags. Character and type filters are in the left column.", points: ["Profiles saves combinations of enabled mods and components.", "History shows recent changes and helps explain what changed."] },
      { chapter: "safety", icon: "⚠", target: "#btn-conflicts", placement: "bottom", focus: "Check conflicts", title: "Avoid incompatibilities", description: "This button looks for enabled mods that change the same assets and shows every competing mod it finds.", points: ["You can disable the competing mod directly from its warning.", "For safety, game changes are blocked while Marvel Rivals is running."] },
      { chapter: "safety", icon: "▣", media: "assets/tutorial/settings-import-maintenance.png", mediaClass: "settings", mediaAlt: "Settings for imported files, game-operation lock, and library maintenance", mediaCaption: "These options define what is preserved and which checks run against the library.", title: "Files and maintenance", description: "The two import options are independent: one keeps an extra archive copy, and the other decides whether external sources are deleted after success.", points: ["The installable copy in mods_storage remains available even without the extra ZIP/RAR/7z backup.", "Bypassing the operation lock allows changes while the game runs; leave it disabled to block them for safety.", "Integrity, pending classifications, and interrupted operations only change something after your review."] },
      { chapter: "safety", icon: "✓", media: "assets/tutorial/settings-backups-appearance.png", mediaClass: "settings", mediaAlt: "Settings for catalog backup, full backup, and appearance", mediaCaption: "Save applies preferences; backup actions open their own review flows.", title: "Backups and appearance", description: "Catalog backup stores entries, tags, covers, components, profiles, and settings. Full backup also includes mod files, media, and personal corrections.", points: ["Extract full backup creates another folder without replacing or enabling the current library.", "Dark theme, light theme, and accent color only change the appearance.", "Save confirms the preferences changed on this screen."] },
    ],
  },
};

let selectedOnboardingLanguage = DEFAULT_LANGUAGE;
let tutorialLanguage = DEFAULT_LANGUAGE;
let tutorialStep = 0;
let tutorialPositionFrame = 0;

function normalizedLanguage(value) { return value === "en" ? "en" : DEFAULT_LANGUAGE; }

function tutorialTargetFor(step) {
  const selectors = Array.isArray(step.target) ? step.target : [step.target];
  for (const selector of selectors.filter(Boolean)) {
    const candidate = document.querySelector(selector);
    if (!candidate || candidate.hidden) continue;
    const rect = candidate.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) return candidate;
  }
  return null;
}

function positionTutorial() {
  cancelAnimationFrame(tutorialPositionFrame);
  tutorialPositionFrame = requestAnimationFrame(() => {
    const overlay = document.getElementById("tutorial-overlay");
    if (!overlay.classList.contains("open")) return;
    const dialog = overlay.querySelector(".tutorial-dialog");
    const spotlight = document.getElementById("tutorial-spotlight");
    const step = TUTORIAL_COPY[tutorialLanguage].steps[tutorialStep];
    const target = tutorialTargetFor(step);
    spotlight.hidden = !target;
    overlay.classList.toggle("is-demo", !target);
    dialog.classList.toggle("is-centered", !target);
    if (!target) {
      dialog.style.left = "50%";
      dialog.style.top = "50%";
      dialog.style.transform = "translate(-50%, -50%)";
      return;
    }
    target.scrollIntoView?.({ block: "nearest", inline: "nearest", behavior: "auto" });
    const rect = target.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
    const viewportHeight = document.documentElement.clientHeight || window.innerHeight;
    const margin = 12, padding = 7, gap = 18;
    const left = Math.max(margin, rect.left - padding);
    const top = Math.max(margin, rect.top - padding);
    const right = Math.min(viewportWidth - margin, rect.right + padding);
    const bottom = Math.min(viewportHeight - margin, rect.bottom + padding);
    Object.assign(spotlight.style, {
      left: `${left}px`, top: `${top}px`,
      width: `${Math.max(1, right - left)}px`, height: `${Math.max(1, bottom - top)}px`,
    });
    document.getElementById("tutorial-focus-name").textContent = step.focus;
    dialog.style.transform = "none";
    const dialogWidth = dialog.offsetWidth;
    const dialogHeight = dialog.offsetHeight;
    const coordinates = {
      bottom: [rect.left + rect.width / 2 - dialogWidth / 2, rect.bottom + gap],
      top: [rect.left + rect.width / 2 - dialogWidth / 2, rect.top - dialogHeight - gap],
      right: [rect.right + gap, rect.top + rect.height / 2 - dialogHeight / 2],
      left: [rect.left - dialogWidth - gap, rect.top + rect.height / 2 - dialogHeight / 2],
    };
    const order = [...new Set([step.placement, "bottom", "top", "right", "left"])];
    const placement = order.find((name) => {
      const [x, y] = coordinates[name];
      return x >= margin && y >= margin && x + dialogWidth <= viewportWidth - margin && y + dialogHeight <= viewportHeight - margin;
    }) || step.placement || "bottom";
    let [x, y] = coordinates[placement];
    x = Math.max(margin, Math.min(viewportWidth - dialogWidth - margin, x));
    y = Math.max(margin, Math.min(viewportHeight - dialogHeight - margin, y));
    dialog.dataset.placement = placement;
    dialog.style.left = `${x}px`;
    dialog.style.top = `${y}px`;
  });
}

function renderLanguageSelection() {
  document.querySelectorAll(".language-choice").forEach((button) => {
    const selected = button.dataset.language === selectedOnboardingLanguage;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-checked", String(selected));
  });
  document.getElementById("language-continue").textContent = selectedOnboardingLanguage === "en" ? "Continue" : "Continuar";
}

function openLanguageSelection() {
  selectedOnboardingLanguage = normalizedLanguage(state.settings.ui_language);
  renderLanguageSelection();
  const overlay = document.getElementById("language-overlay");
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  document.querySelector(`.language-choice[data-language="${selectedOnboardingLanguage}"]`)?.focus();
}

function renderTutorial() {
  const copy = TUTORIAL_COPY[tutorialLanguage];
  const step = copy.steps[tutorialStep];
  const chapter = copy.chapters.find((item) => item.id === step.chapter) || copy.chapters[0];
  const final = tutorialStep === copy.steps.length - 1;
  document.getElementById("tutorial-kicker").textContent = `${copy.kicker} · ${chapter.label}`;
  document.getElementById("tutorial-title").textContent = step.title;
  document.getElementById("tutorial-counter").textContent = copy.counter(tutorialStep + 1, copy.steps.length);
  document.getElementById("tutorial-progress-bar").style.width = `${((tutorialStep + 1) / copy.steps.length) * 100}%`;
  document.getElementById("tutorial-icon").textContent = step.icon;
  document.getElementById("tutorial-description").textContent = step.description;
  document.getElementById("tutorial-points").innerHTML = step.points.map((point) => `<li>${escapeHtml(point)}</li>`).join("");
  const dialog = document.querySelector("#tutorial-overlay .tutorial-dialog");
  const media = document.getElementById("tutorial-media");
  const mediaImage = document.getElementById("tutorial-media-image");
  const mediaFocus = document.getElementById("tutorial-media-focus");
  const hasMedia = Boolean(step.media);
  dialog.classList.toggle("has-media", hasMedia);
  dialog.classList.toggle("has-settings-media", step.mediaClass === "settings");
  media.hidden = !hasMedia;
  media.className = `tutorial-media${step.mediaClass ? ` media-${step.mediaClass}` : ""}`;
  if (hasMedia) {
    mediaImage.alt = step.mediaAlt || "";
    mediaImage.onload = positionTutorial;
    if (!mediaImage.src.endsWith(step.media)) mediaImage.src = step.media;
    document.getElementById("tutorial-media-caption").textContent = step.mediaCaption || "";
    mediaFocus.hidden = !step.mediaFocus;
    if (step.mediaFocus) {
      Object.assign(mediaFocus.style, {
        left: `${step.mediaFocus.x}%`, top: `${step.mediaFocus.y}%`,
        width: `${step.mediaFocus.width}%`, height: `${step.mediaFocus.height}%`,
      });
      mediaFocus.querySelector("span").textContent = step.mediaFocus.label || "";
    }
  } else {
    mediaImage.removeAttribute("src");
    mediaFocus.hidden = true;
  }
  const stepMap = document.getElementById("tutorial-step-map");
  stepMap.setAttribute("aria-label", tutorialLanguage === "en" ? "Tutorial chapters" : "Capítulos do tutorial");
  stepMap.innerHTML = copy.chapters.map((item) => {
    const firstStep = copy.steps.findIndex((candidate) => candidate.chapter === item.id);
    const selected = item.id === step.chapter;
    return `<button type="button" data-step="${firstStep}" class="${selected ? "selected" : ""}" aria-label="${escapeHtml(item.label)}" aria-current="${selected ? "step" : "false"}"><span>${item.icon}</span><b>${escapeHtml(item.label)}</b></button>`;
  }).join("");
  const back = document.getElementById("tutorial-back");
  back.textContent = copy.back;
  back.hidden = tutorialStep === 0;
  document.getElementById("tutorial-next").textContent = copy.next;
  document.getElementById("tutorial-review").textContent = copy.review;
  document.getElementById("tutorial-understand").textContent = copy.done;
  document.querySelector(".tutorial-next-actions").hidden = final;
  document.getElementById("tutorial-final-actions").hidden = !final;
  positionTutorial();
}

function openTutorial(language = state.settings.ui_language) {
  tutorialLanguage = normalizedLanguage(language);
  tutorialStep = 0;
  document.getElementById("tutorial-error").textContent = "";
  const overlay = document.getElementById("tutorial-overlay");
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  renderTutorial();
  document.getElementById("tutorial-next").focus();
}

function closeTutorial() {
  const overlay = document.getElementById("tutorial-overlay");
  overlay.classList.remove("open");
  overlay.setAttribute("aria-hidden", "true");
  document.getElementById("tutorial-spotlight").hidden = true;
  cancelAnimationFrame(tutorialPositionFrame);
}

document.querySelectorAll(".language-choice").forEach((button) => {
  button.onclick = () => { selectedOnboardingLanguage = normalizedLanguage(button.dataset.language); renderLanguageSelection(); };
});
document.getElementById("language-continue").onclick = async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  document.getElementById("language-error").textContent = "";
  try {
    state.settings = await api().save_settings({ ui_language: selectedOnboardingLanguage, language_selected: true });
    window.setUiLanguage?.(selectedOnboardingLanguage);
    const overlay = document.getElementById("language-overlay");
    overlay.classList.remove("open");
    overlay.setAttribute("aria-hidden", "true");
    openTutorial(selectedOnboardingLanguage);
  } catch (error) {
    document.getElementById("language-error").textContent = selectedOnboardingLanguage === "en" ? "Could not save the language." : "Não foi possível salvar o idioma.";
  } finally { button.disabled = false; }
};
document.getElementById("tutorial-back").onclick = () => { if (tutorialStep > 0) { tutorialStep -= 1; renderTutorial(); } };
document.getElementById("tutorial-next").onclick = () => { if (tutorialStep < TUTORIAL_COPY[tutorialLanguage].steps.length - 1) { tutorialStep += 1; renderTutorial(); } };
document.getElementById("tutorial-review").onclick = () => { tutorialStep = 0; renderTutorial(); };
document.getElementById("tutorial-step-map").onclick = (event) => {
  const button = event.target.closest("button[data-step]");
  if (!button) return;
  tutorialStep = Math.max(0, Math.min(TUTORIAL_COPY[tutorialLanguage].steps.length - 1, Number(button.dataset.step) || 0));
  renderTutorial();
};
document.getElementById("tutorial-overlay").onkeydown = (event) => {
  if (event.key === "ArrowLeft" && tutorialStep > 0) { event.preventDefault(); tutorialStep -= 1; renderTutorial(); }
  if (event.key === "ArrowRight" && tutorialStep < TUTORIAL_COPY[tutorialLanguage].steps.length - 1) { event.preventDefault(); tutorialStep += 1; renderTutorial(); }
};
window.addEventListener("resize", positionTutorial);
window.addEventListener("scroll", positionTutorial, true);
document.getElementById("tutorial-understand").onclick = async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  document.getElementById("tutorial-error").textContent = "";
  try {
    state.settings = await api().save_settings({ tutorial_completed: true });
    closeTutorial();
  } catch (error) {
    document.getElementById("tutorial-error").textContent = tutorialLanguage === "en" ? "Could not save your choice." : "Não foi possível salvar sua escolha.";
  } finally { button.disabled = false; }
};

function previewVolume() {
  const value = Number(state.settings.preview_volume);
  return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0.5;
}

function formatModSize(sizeMb) {
  const mb = Number(sizeMb) || 0;
  if (mb >= 1024) return `${(mb / 1024).toFixed(mb >= 10240 ? 1 : 2)} GB`;
  return `${mb.toFixed(2)} MB`;
}

function applyPreviewVolume() {
  const volume = previewVolume();
  document.querySelectorAll("audio, video").forEach((media) => { media.volume = volume; });
  const input = document.getElementById("preview-volume");
  const label = document.getElementById("preview-volume-value");
  if (input) input.value = String(Math.round(volume * 100));
  if (label) label.textContent = `${Math.round(volume * 100)}%`;
  document.getElementById("btn-volume")?.classList.toggle("is-muted", volume === 0);
}

function isHexColor(value) {
  return typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);
}

function hexToRgb(hex) {
  const normalized = (isHexColor(hex) ? hex : DEFAULT_ACCENT).slice(1);
  return {
    r: Number.parseInt(normalized.slice(0, 2), 16),
    g: Number.parseInt(normalized.slice(2, 4), 16),
    b: Number.parseInt(normalized.slice(4, 6), 16),
  };
}

function applyAccentColor(color) {
  const accent = isHexColor(color) ? color : DEFAULT_ACCENT;
  const { r, g, b } = hexToRgb(accent);
  const root = document.documentElement;
  root.style.setProperty("--accent", accent);
  root.style.setProperty("--accent-hover", accent);
  root.style.setProperty("--accent-dim", `rgba(${r}, ${g}, ${b}, 0.15)`);
  root.style.setProperty("--accent-dim-border", `rgba(${r}, ${g}, ${b}, 0.35)`);
}

function applyThemeMode(theme) {
  const normalized = theme === "light" ? "light" : DEFAULT_THEME;
  document.documentElement.classList.toggle("theme-light", normalized === "light");
}

function displayModName(name) {
  const value = String(name || "");
  return state.settings.hide_file_suffix ? value.replace(/_[0-9]{7,}_P$/i, "") : value;
}

function modTypes(mod) {
  const types = Array.isArray(mod.types) && mod.types.length ? mod.types : [mod.type || "Unknown"];
  return [...new Set(types.filter(Boolean))];
}

function modTypeClass(type) {
  return `type-${String(type || "Unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

function api() {
  return window.pywebview.api;
}

document.addEventListener("play", (event) => {
  if (event.target instanceof HTMLMediaElement) event.target.volume = previewVolume();
}, true);

async function refreshModInState(modId) {
  if (typeof detailMetadataCache !== "undefined") detailMetadataCache.delete(modId);
  const fresh = await api().get_mod_details(modId, false);
  if (!fresh) return null;
  const index = state.mods.findIndex((mod) => mod.id === modId);
  if (index >= 0) state.mods[index] = preserveModThumbnail(fresh, state.mods[index]);
  return fresh;
}

function preserveModThumbnail(mod, previous) {
  if (mod && previous && mod.id === previous.id && mod.thumbnail_key
      && mod.thumbnail_key === previous.thumbnail_key && !mod.image_url && previous.image_url) {
    mod.image_url = previous.image_url;
    mod.image_urls = [previous.image_url];
  }
  return mod;
}

function renderLocalChange() {
  if (typeof detailMetadataCache !== "undefined") detailMetadataCache.clear();
  renderMods.cardCache?.clear();
  scheduleConflictRefresh();
  safeRender(renderCharacters);
  safeRender(renderTypes);
  safeRender(renderTags);
  safeRender(renderMods);
  safeRender(renderHeaderCount);
}

function thumbnailRequestKey(modId, thumbnailKey) {
  return JSON.stringify([modId, thumbnailKey]);
}

function resetThumbnailQueue(scroll) {
  state.thumbnailObserver?.disconnect();
  if (state.thumbnailFallbackRoot && state.thumbnailFallbackHandler) {
    state.thumbnailFallbackRoot.removeEventListener("scroll", state.thumbnailFallbackHandler);
    window.removeEventListener("resize", state.thumbnailFallbackHandler);
  }
  // Workers já em execução conservam seu pending até terminar. Só a fila que
  // ainda não foi despachada pertence aos cartões que serão substituídos.
  for (const request of state.thumbnailQueue) state.thumbnailPending.delete(request.token);
  state.thumbnailQueue = [];
  state.thumbnailCards = new Map();
  state.thumbnailGeneration = (state.thumbnailGeneration || 0) + 1;
  state.thumbnailObserver = null;
  state.thumbnailFallbackRoot = null;
  state.thumbnailFallbackHandler = null;
  const generation = state.thumbnailGeneration;
  const updateVisibility = (card, visible) => {
    if (state.thumbnailGeneration !== generation || state.thumbnailCards.get(card.dataset.id) !== card) return;
    card.dataset.thumbnailNear = visible ? "true" : "false";
    if (visible) queueModThumbnail(state.mods.find((mod) => mod.id === card.dataset.id), card);
  };
  if (typeof IntersectionObserver === "function") {
    state.thumbnailObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) updateVisibility(entry.target, entry.isIntersecting);
    }, { root: scroll, rootMargin: "400px 0px", threshold: 0 });
  } else {
    // WebViews antigos continuam limitados à área próxima da rolagem.
    let scheduled = false;
    const scanVisible = () => {
      if (scheduled) return;
      scheduled = true;
      const schedule = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (callback) => setTimeout(callback, 0);
      schedule(() => {
        scheduled = false;
        if (state.thumbnailGeneration !== generation) return;
        const bounds = scroll.getBoundingClientRect();
        for (const card of state.thumbnailCards.values()) {
          const rect = card.getBoundingClientRect();
          updateVisibility(card, rect.bottom >= bounds.top - 400 && rect.top <= bounds.bottom + 400);
        }
      });
    };
    state.thumbnailFallbackRoot = scroll;
    state.thumbnailFallbackHandler = scanVisible;
    scroll.addEventListener("scroll", scanVisible, { passive: true });
    window.addEventListener("resize", scanVisible);
  }
}

function observeModThumbnail(mod, card) {
  card.dataset.thumbnailKey = mod.thumbnail_key || "";
  card.dataset.thumbnailNear = "false";
  state.thumbnailCards.set(mod.id, card);
  if (mod.image_url || !mod.thumbnail_key) return;
  if (state.thumbnailObserver) state.thumbnailObserver.observe(card);
  else state.thumbnailFallbackHandler?.();
}

function queueModThumbnail(mod, card = state.thumbnailCards?.get(mod?.id)) {
  const hasCover = mod?.image || (Array.isArray(mod?.images) && mod.images.length > 0);
  if (!mod?.id || !hasCover || !mod.thumbnail_key || mod.image_url || card?.dataset.thumbnailNear !== "true") return;
  const token = thumbnailRequestKey(mod.id, mod.thumbnail_key);
  if (state.thumbnailPending.has(token)) return;
  state.thumbnailPending.add(token);
  state.thumbnailQueue.push({ modId: mod.id, thumbnailKey: mod.thumbnail_key, token,
                             generation: state.thumbnailGeneration, card });
  drainThumbnailQueue();
}

function drainThumbnailQueue() {
  if (document.getElementById("mod-detail-overlay")?.classList.contains("open")) return;
  while (state.thumbnailWorkers < THUMBNAIL_WORKER_LIMIT && state.thumbnailQueue.length) {
    const request = state.thumbnailQueue.shift();
    const mod = state.mods.find((item) => item.id === request.modId);
    if (request.generation !== state.thumbnailGeneration || request.card !== state.thumbnailCards?.get(request.modId)
        || request.card.isConnected === false || request.card.dataset.thumbnailNear !== "true"
        || !mod || mod.image_url || mod.thumbnail_key !== request.thumbnailKey) {
      state.thumbnailPending.delete(request.token);
      continue;
    }
    state.thumbnailWorkers += 1;
    void loadModThumbnail(request).finally(() => {
      state.thumbnailWorkers -= 1;
      drainThumbnailQueue();
    });
  }
}

async function loadModThumbnail(request) {
  try {
    const result = await api().get_mod_thumbnail(request.modId);
    if (!result?.ok || !result.image_url) return;
    const mod = state.mods.find((item) => item.id === request.modId);
    if (!mod || mod.thumbnail_key !== request.thumbnailKey || result.thumbnail_key !== request.thumbnailKey) return;
    mod.image_url = result.image_url;
    mod.image_urls = [result.image_url];
    const card = state.thumbnailCards?.get(request.modId);
    if (card?.dataset.thumbnailKey !== request.thumbnailKey) return;
    const cover = card?.querySelector(".mod-cover");
    if (!cover) return;
    state.thumbnailObserver?.unobserve(card);
    cover.classList.remove("no-cover");
    cover.classList.add("has-cover");
    cover.style.backgroundImage = `url('${result.image_url}')`;
    cover.textContent = "";
  } catch (_) {
    // A capa é opcional; o card continua utilizável se um arquivo falhar.
  } finally {
    state.thumbnailPending.delete(request.token);
  }
}

// ---------------------------------------------------------
// Titlebar
// ---------------------------------------------------------
document.getElementById("btn-minimize").onclick = () => api().minimize();
document.getElementById("btn-maximize").onclick = () => api().toggle_maximize();
document.getElementById("btn-close").onclick = () => api().close();

document.getElementById("btn-refresh").onclick = () => reloadAll();
function syncViewButtons() {
  document.getElementById("btn-list-view").classList.toggle("active", state.view === "list");
  document.getElementById("btn-grid-view").classList.toggle("active", state.view === "grid");
}

function setViewMode(view, { persist = false, render = true } = {}) {
  state.view = view === "grid" ? "grid" : "list";
  syncViewButtons();
  if (render) renderMods();
  if (persist) {
    void api().save_settings({ view_mode: state.view })
      .then((settings) => { state.settings = settings; })
      .catch(() => {});
  }
}

document.getElementById("btn-list-view").onclick = () => setViewMode("list", { persist: true });
document.getElementById("btn-grid-view").onclick = () => setViewMode("grid", { persist: true });

function renderBulkActions() {
  const selection = state.selectedModIds;
  const visibleIds = new Set(state.mods.map((mod) => mod.id));
  [...selection].forEach((id) => { if (!visibleIds.has(id)) selection.delete(id); });
  const wrapper = document.getElementById("bulk-actions");
  wrapper.hidden = selection.size === 0;
  document.getElementById("bulk-selection-count").textContent = `${selection.size} selecionado${selection.size === 1 ? "" : "s"}`;
  const selectedActive = state.mods.filter((mod) => selection.has(mod.id) && mod.enabled).length;
  const conflictButton = document.getElementById("btn-bulk-conflicts");
  conflictButton.hidden = selection.size < 2 || selectedActive < 2;
  conflictButton.textContent = `⚠ Marcar conflito (${selectedActive})`;
}

async function setSelectedModsEnabled(enable) {
  const selectedIds = [...state.selectedModIds];
  if (!selectedIds.length) return;
  const action = enable ? "ativar" : "desativar";
  if (!confirm(`${action[0].toUpperCase()}${action.slice(1)} ${selectedIds.length} mod(s) selecionado(s)?`)) return;
  const result = await api().set_mods_enabled(selectedIds, enable);
  const changed = new Set(result.changed || []);
  state.mods.forEach((mod) => { if (changed.has(mod.id)) mod.enabled = enable; });
  if (result.errors?.length) alert(`${result.errors.length} mod(s) não puderam ser alterados.`);
  renderLocalChange();
  renderBulkActions();
}

document.getElementById("btn-bulk-enable").onclick = () => setSelectedModsEnabled(true);
document.getElementById("btn-bulk-disable").onclick = () => setSelectedModsEnabled(false);
document.getElementById("btn-bulk-conflicts").onclick = () => markSelectedModsAsConflicting();
document.getElementById("btn-bulk-clear").onclick = () => {
  state.selectedModIds.clear();
  renderMods();
};

async function markSelectedModsAsConflicting() {
  const selectedActiveIds = state.mods
    .filter((mod) => state.selectedModIds.has(mod.id) && mod.enabled)
    .map((mod) => mod.id);
  if (selectedActiveIds.length < 2) {
    alert("Selecione pelo menos dois mods ativos para marcar um conflito.");
    return;
  }
  if (!confirm(`Marcar conflito manual entre ${selectedActiveIds.length} mod(s) selecionado(s)? O alerta aparecerá enquanto eles estiverem ativos.`)) return;

  const button = document.getElementById("btn-bulk-conflicts");
  button.disabled = true;
  try {
    const result = await api().set_manual_conflicts(selectedActiveIds);
    if (!result?.ok) {
      alert(result?.error || "Não foi possível marcar o conflito.");
      return;
    }
    await refreshConflictIndicators();
  } finally {
    button.disabled = false;
    renderBulkActions();
  }
}

// ---------------------------------------------------------
// Dropdowns genéricos (sort / tags)
// ---------------------------------------------------------
document.querySelectorAll(".dropdown").forEach((dd) => {
  const btn = dd.querySelector(".dropdown-btn");
  const menu = dd.querySelector(".dropdown-menu");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    document.querySelectorAll(".dropdown-menu.open").forEach((m) => {
      if (m !== menu) m.classList.remove("open");
    });
    menu.classList.toggle("open");
  });
});
document.addEventListener("click", () => {
  document.querySelectorAll(".dropdown-menu.open").forEach((m) => m.classList.remove("open"));
});

document.querySelectorAll("#sort-dropdown .dropdown-item").forEach((item) => {
  item.addEventListener("click", () => {
    state.sort = item.dataset.sort;
    document.querySelectorAll("#sort-dropdown .dropdown-item").forEach((i) => i.classList.remove("selected"));
    item.classList.add("selected");
    document.querySelector("#sort-dropdown .dropdown-btn").textContent = "↕ " + item.textContent;
    renderMods();
  });
});

// ---------------------------------------------------------
// Sidebar: collapse sections
// ---------------------------------------------------------
document.querySelectorAll(".sidebar-heading[data-target]").forEach((h) => {
  h.addEventListener("click", () => {
    const target = document.getElementById(h.dataset.target);
    h.classList.toggle("collapsed");
    target.classList.toggle("collapsed");
  });
});

// ---------------------------------------------------------
// Busca
// ---------------------------------------------------------
document.getElementById("search-input").addEventListener("input", (e) => {
  state.search = e.target.value.toLowerCase();
  renderMods();
  renderFilterCounts();
});

function matchesActiveFilters(mod, ignore = "") {
  if (mod.parent_background_id) return false;
  if (ignore !== "character" && state.activeCharacter && mod.character !== state.activeCharacter) return false;
  if (ignore !== "skin" && state.activeSkin) {
    const matchesBackgroundLocation = mod.character === "Backgrounds" && (mod.background_locations || []).includes(state.activeSkin);
    if ((mod.skin || "Default") !== state.activeSkin && !matchesBackgroundLocation) return false;
  }
  const types = modTypes(mod);
  if (ignore !== "types" && state.activeTypes.size && ![...state.activeTypes].every((type) => types.includes(type))) return false;
  const tags = Array.isArray(mod.tags) ? mod.tags : [];
  if (ignore !== "tags" && state.activeTags.size && ![...state.activeTags].every((tag) => tags.includes(tag))) return false;
  if (state.search && !String(mod.name || "").toLocaleLowerCase().includes(state.search)) return false;
  return true;
}

function contextualCount(ignore, predicate) {
  return state.mods.filter((mod) => matchesActiveFilters(mod, ignore) && predicate(mod)).length;
}

function renderFilterCounts() {
  renderCharacters();
  if (!document.getElementById("skin-sidebar").hidden) renderSkins();
  renderTypes();
  renderTags();
}

// ---------------------------------------------------------
// Render: Characters (sidebar)
// ---------------------------------------------------------
function renderCharacters() {
  const wrap = document.getElementById("characters-group");
  wrap.innerHTML = "";
  state.characters.forEach((c) => {
    const row = document.createElement("div");
    row.className = "filter-row" + (state.activeCharacter === c.name ? " active" : "");
    const icon = c.hero_icon_url
      ? `<img class="filter-character-icon" src="${c.hero_icon_url}" alt="" aria-hidden="true">`
      : "";
    const count = contextualCount("character", (mod) => mod.character === c.name);
    row.innerHTML = `<span class="filter-character-label">${icon}<span class="filter-character-name">${escapeHtml(c.name)}</span></span><span class="filter-count">${count}</span>`;
    row.onclick = () => {
      const deselecting = state.activeCharacter === c.name;
      state.activeCharacter = deselecting ? null : c.name;
      state.activeSkin = null;
      if (deselecting) {
        state.characterSkins = [];
        document.getElementById("skin-sidebar").hidden = true;
      } else {
        loadCharacterSkins(c.name);
      }
      renderFilterCounts();
      renderMods();
    };
    if (c.name === "Backgrounds") {
      const restore = document.createElement("button");
      restore.className = "background-restore";
      restore.textContent = "Restaurar padrão";
      restore.title = "Restaura o MoviesBink original e desativa todos os Backgrounds";
      restore.onclick = async (event) => {
        event.stopPropagation();
        if (!confirm("Restaurar o MoviesBink original? Todos os mods de Background serão desativados.")) return;
        const result = await api().restore_cinematic_defaults();
        if (!result?.ok) return alert(result?.error || "Não foi possível restaurar os Backgrounds.");
        await reloadAll();
      };
      row.appendChild(restore);
    }
    wrap.appendChild(row);
  });
}

async function loadCharacterSkins(character) {
  state.characterSkins = await api().get_character_skins(character);
  document.getElementById("skins-heading").textContent = `${character} skins`;
  document.getElementById("skin-sidebar").hidden = false;
  renderSkins();
}

function renderSkins() {
  const wrap = document.getElementById("skins-group");
  wrap.innerHTML = "";
  state.characterSkins.forEach((skin) => {
    const row = document.createElement("div");
    row.className = "filter-row" + (state.activeSkin === skin.name ? " active" : "");
    const icon = skin.skin_icon_url
      ? `<img class="filter-skin-icon" src="${skin.skin_icon_url}" alt="" loading="lazy" aria-hidden="true">`
      : "";
    const count = contextualCount("skin", (mod) => {
      const background = mod.character === "Backgrounds" && (mod.background_locations || []).includes(skin.name);
      return (mod.skin || "Default") === skin.name || background;
    });
    row.innerHTML = `<span class="filter-skin-label">${icon}<span class="filter-skin-name">${escapeHtml(skin.name)}</span></span><span class="filter-count">${count}</span>`;
    row.onclick = () => {
      state.activeSkin = state.activeSkin === skin.name ? null : skin.name;
      renderFilterCounts();
      renderMods();
    };
    wrap.appendChild(row);
  });
}

// ---------------------------------------------------------
// Render: Types (sidebar, pills)
// ---------------------------------------------------------
function renderTypes() {
  const wrap = document.getElementById("types-group");
  wrap.innerHTML = "";
  // Unknown continua disponível mesmo quando nenhum mod atual o utiliza:
  // assim é possível filtrar rapidamente uma importação futura sem depender
  // de outro scan para o item aparecer na barra lateral.
  const types = [...new Set(["Unknown", ...(state.types || [])])];
  const typeOrder = ["Audio", "Mesh", "Texture", "UI", "Physics", "Unknown"];
  types.sort((a, b) => {
    const ai = typeOrder.indexOf(a);
    const bi = typeOrder.indexOf(b);
    return (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi) || String(a).localeCompare(String(b));
  });
  types.forEach((t) => {
    const pill = document.createElement("div");
    pill.className = "type-pill" + (state.activeTypes.has(t) ? " active" : "");
    const otherTypes = [...state.activeTypes].filter((type) => type !== t);
    const count = contextualCount("types", (mod) => {
      const typesForMod = modTypes(mod);
      return typesForMod.includes(t) && otherTypes.every((type) => typesForMod.includes(type));
    });
    pill.textContent = `${t} ${count}`;
    pill.onclick = () => {
      if (state.activeTypes.has(t)) state.activeTypes.delete(t);
      else state.activeTypes.add(t);
      renderFilterCounts();
      renderMods();
    };
    wrap.appendChild(pill);
  });
}

function renderTags() {
  const menu = document.getElementById("tags-menu");
  const button = document.querySelector("#tags-dropdown .dropdown-btn");
  button.textContent = state.activeTags.size === 0 ? "🏷 Todas as tags" : `🏷 Tags (${state.activeTags.size})`;
  menu.innerHTML = "";
  [{ name: "Todas as tags", count: "" }, ...state.tags].forEach((tag) => {
    const row = document.createElement("div");
    const selected = tag.name === "Todas as tags" ? state.activeTags.size === 0 : state.activeTags.has(tag.name);
    row.className = "dropdown-item" + (selected ? " selected" : "");
    const otherTags = [...state.activeTags].filter((value) => value !== tag.name);
    const count = tag.name === "Todas as tags" ? "" : contextualCount("tags", (mod) => {
      const tags = Array.isArray(mod.tags) ? mod.tags : [];
      return tags.includes(tag.name) && otherTags.every((value) => tags.includes(value));
    });
    row.textContent = tag.name === "Todas as tags" ? tag.name : `${tag.name} (${count})`;
    row.onclick = (event) => {
      event.stopPropagation();
      if (tag.name === "Todas as tags") state.activeTags.clear();
      else if (state.activeTags.has(tag.name)) state.activeTags.delete(tag.name);
      else state.activeTags.add(tag.name);
      renderMods(); renderFilterCounts();
    };
    menu.appendChild(row);
  });
}

// ---------------------------------------------------------
// Filtro + ordenação combinados
// ---------------------------------------------------------
function filteredMods() {
  let rows = state.mods.filter((mod) => matchesActiveFilters(mod));

  rows = rows.slice().sort((a, b) => {
    // Com dois ou mais filtros, os mods que satisfazem mais seleções sobem:
    // Mesh + Texture vem antes de só Mesh; depois vêm os demais híbridos.
    if (state.activeTypes.size) {
      const aTypes = a.types || [a.type || "Unknown"];
      const bTypes = b.types || [b.type || "Unknown"];
      const aMatches = aTypes.filter((type) => state.activeTypes.has(type)).length;
      const bMatches = bTypes.filter((type) => state.activeTypes.has(type)).length;
      if (aMatches !== bMatches) return bMatches - aMatches;
      if (aTypes.length !== bTypes.length) return bTypes.length - aTypes.length;
    }
    switch (state.sort) {
      case "name-desc":
        return b.name.localeCompare(a.name);
      case "newest":
        return (b.created_at || "").localeCompare(a.created_at || "");
      case "oldest":
        return (a.created_at || "").localeCompare(b.created_at || "");
      case "priority":
        return (b.priority || 1) - (a.priority || 1);
      default:
        return a.name.localeCompare(b.name);
    }
  });

  return rows;
}

function openModRemovalDialog(mod, { permanent = false } = {}) {
  document.getElementById("mod-removal-overlay")?.remove();
  const previousFocus = document.activeElement;
  const english = window.getUiLanguage?.() === "en";
  const text = (portuguese, englishText) => english ? englishText : portuguese;
  const copy = permanent ? {
    title: text("Excluir permanentemente", "Delete permanently"),
    question: text("Excluir este mod e todos os seus dados?", "Delete this mod and all of its data?"),
    removed: text("Pacotes, imagens da galeria e arquivos ZIP/RAR/7z serão apagados.", "Packages, gallery images, and ZIP/RAR/7z archives will be deleted."),
    warning: text("Esta ação não pode ser desfeita.", "This action cannot be undone."),
    confirm: text("Continuar", "Continue"),
    finalTitle: text("Confirmação final", "Final confirmation"),
    finalQuestion: text("Tem certeza de que deseja apagar tudo deste mod?", "Are you sure you want to delete everything for this mod?"),
    finalRemoved: text("O registro, os pacotes, a galeria e todos os arquivos guardados serão apagados agora.", "The entry, packages, gallery, and every stored file will be deleted now."),
    finalWarning: text("Depois deste clique, nenhum dado poderá ser recuperado pelo Manager.", "After this click, the Manager cannot recover any of this data."),
    finalConfirm: text("Sim, apagar tudo", "Yes, delete everything"),
    busy: text("Excluindo…", "Deleting…"),
    error: text("Não foi possível excluir o mod permanentemente.", "Could not permanently delete the mod."),
  } : {
    title: text("Remover mod", "Remove mod"),
    question: text("Remover este mod do Manager?", "Remove this mod from the Manager?"),
    removed: text("Os pacotes instaláveis e o registro do mod serão removidos.", "The installable packages and mod entry will be removed."),
    warning: text("Imagens da galeria e arquivos ZIP/RAR/7z serão preservados em mods_storage.", "Gallery images and ZIP/RAR/7z archives will be kept in mods_storage."),
    confirm: text("Remover mod", "Remove mod"),
    busy: text("Removendo…", "Removing…"),
    error: text("Não foi possível remover o mod.", "Could not remove the mod."),
  };
  const overlay = document.createElement("div");
  overlay.id = "mod-removal-overlay";
  overlay.className = "modal-overlay open mod-removal-overlay";
  overlay.dataset.step = permanent ? "review" : "confirm";
  overlay.innerHTML = `<section class="mod-removal-dialog ${permanent ? "is-permanent" : ""}" role="alertdialog" aria-modal="true" aria-labelledby="mod-removal-title" aria-describedby="mod-removal-description" tabindex="-1"><header><span class="mod-removal-icon" aria-hidden="true">${permanent ? "!" : "−"}</span><div><b id="mod-removal-title">${copy.title}</b><small>${escapeHtml(mod.name)}</small></div><button class="icon-btn mod-removal-close" aria-label="${text("Fechar", "Close")}">✕</button></header><div class="mod-removal-body" id="mod-removal-description"><h3 class="mod-removal-question">${copy.question}</h3><div class="mod-removal-impact"><p class="mod-removal-removed"><span aria-hidden="true">${permanent ? "×" : "−"}</span><span class="mod-removal-removed-text">${copy.removed}</span></p><p class="mod-removal-warning ${permanent ? "irreversible" : "preserved"}"><span aria-hidden="true">${permanent ? "!" : "✓"}</span><span class="mod-removal-warning-text">${copy.warning}</span></p></div><p class="dialog-error mod-removal-error" role="alert"></p></div><footer><button class="btn mod-removal-cancel">${text("Cancelar", "Cancel")}</button><button class="btn mod-removal-confirm">${copy.confirm}</button></footer></section>`;
  const dialog = overlay.querySelector(".mod-removal-dialog");
  const cancel = overlay.querySelector(".mod-removal-cancel");
  const confirmButton = overlay.querySelector(".mod-removal-confirm");
  const close = () => {
    if (overlay.dataset.busy === "true") return;
    overlay.remove();
    previousFocus?.focus?.();
  };
  overlay.querySelector(".mod-removal-close").onclick = close;
  cancel.onclick = close;
  overlay.onclick = event => { if (event.target === overlay) close(); };
  overlay.onkeydown = event => {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (event.key !== "Tab") return;
    const controls = [overlay.querySelector(".mod-removal-close"), cancel, confirmButton].filter(item => !item.disabled);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    else if (!overlay.contains(document.activeElement)) { event.preventDefault(); cancel.focus(); }
  };
  confirmButton.onclick = async () => {
    if (permanent && overlay.dataset.step !== "final") {
      overlay.dataset.step = "final";
      dialog.classList.add("is-final");
      overlay.querySelector("#mod-removal-title").textContent = copy.finalTitle;
      overlay.querySelector(".mod-removal-question").textContent = copy.finalQuestion;
      overlay.querySelector(".mod-removal-removed-text").textContent = copy.finalRemoved;
      overlay.querySelector(".mod-removal-warning-text").textContent = copy.finalWarning;
      confirmButton.textContent = copy.finalConfirm;
      overlay.querySelector(".mod-removal-error").textContent = "";
      cancel.focus();
      return;
    }
    overlay.dataset.busy = "true";
    dialog.setAttribute("aria-busy", "true");
    cancel.disabled = true;
    confirmButton.disabled = true;
    confirmButton.textContent = copy.busy;
    overlay.querySelector(".mod-removal-error").textContent = "";
    try {
      const result = permanent ? await api().delete_mod_permanently(mod.id) : await api().delete_mod(mod.id);
      if (!result?.ok) throw new Error(window.uiText?.(result?.error || copy.error) || result?.error || copy.error);
      overlay.remove();
      state.mods = state.mods.filter(item => item.id !== mod.id);
      state.selectedModIds.delete(mod.id);
      if (state.focusedModId === mod.id) state.focusedModId = null;
      renderLocalChange();
    } catch (error) {
      overlay.dataset.busy = "false";
      dialog.setAttribute("aria-busy", "false");
      cancel.disabled = false;
      confirmButton.disabled = false;
      confirmButton.textContent = permanent && overlay.dataset.step === "final" ? copy.finalConfirm : copy.confirm;
      overlay.querySelector(".mod-removal-error").textContent = error?.message || copy.error;
    }
  };
  document.body.appendChild(overlay);
  cancel.focus();
  return overlay;
}

// ---------------------------------------------------------
// Render: lista de mods
// ---------------------------------------------------------
function renderMods() {
  const renderSerial = renderMods.serial = (renderMods.serial || 0) + 1;
  const cardCache = renderMods.cardCache ||= new Map();
  const scroll = document.getElementById("mods-scroll");
  const rows = filteredMods();
  resetThumbnailQueue(scroll);
  scroll.innerHTML = "";
  scroll.classList.toggle("grid-view", state.view === "grid");

  if (rows.length === 0) {
    scroll.innerHTML = `<div class="empty-state">Nenhum mod encontrado.<br/>Clique em "＋ Add Mod" pra instalar o primeiro.</div>`;
    return;
  }

  if (state.focusedModId && !rows.some((mod) => mod.id === state.focusedModId)) state.focusedModId = null;

  const selectRange = (targetId) => {
    const anchorId = state.lastSelectedModId;
    const targetIndex = rows.findIndex((item) => item.id === targetId);
    const anchorIndex = rows.findIndex((item) => item.id === anchorId);
    if (!state.selectedModIds.size || targetIndex < 0 || anchorIndex < 0) {
      state.selectedModIds.add(targetId);
      state.lastSelectedModId = targetId;
      return;
    }
    const [from, to] = [anchorIndex, targetIndex].sort((a, b) => a - b);
    rows.slice(from, to + 1).forEach((item) => state.selectedModIds.add(item.id));
  };

  const selectMod = (mod, event, { toggle = false } = {}) => {
    state.keyboardNavigation = false;
    if (event?.shiftKey && state.selectedModIds.size) {
      selectRange(mod.id);
    } else if (toggle) {
      if (state.selectedModIds.has(mod.id)) state.selectedModIds.delete(mod.id);
      else state.selectedModIds.add(mod.id);
      state.lastSelectedModId = mod.id;
    } else {
      state.selectedModIds.add(mod.id);
      state.lastSelectedModId = mod.id;
    }
    state.focusedModId = mod.id;
    renderMods();
  };

  const appendChunk = (start = 0) => {
    if (renderSerial !== renderMods.serial) return;
    const end = Math.min(rows.length, start + 18);
    rows.slice(start, end).forEach((mod) => {
    const conflictInfo = mod.enabled ? state.conflictsByMod.get(mod.id) : null;
    const cardSignature = JSON.stringify([
      mod.name, mod.character, mod.skin_icon_url, mod.hero_icon_url, mod.image_url,
      mod.tags, modTypes(mod), mod.catalog_size_mb, mod.size_mb, mod.enabled,
      state.settings.show_type_badge, Boolean(state.activeCharacter),
      conflictInfo?.count || 0, conflictInfo?.ties || 0, conflictInfo?.resolvedByPriority || 0,
    ]);
    const cachedCard = cardCache.get(mod.id);
    if (cachedCard?.signature === cardSignature) {
      const card = cachedCard.card;
      card.className = "mod-card" + (state.settings.show_type_badge ? " show-type-badge" : "") + (state.detailsModId === mod.id ? " selected" : "") + (state.selectedModIds.has(mod.id) ? " selection-selected" : "") + (state.focusedModId === mod.id ? " keyboard-focused" : "") + (conflictInfo ? " has-conflict" : "");
      const checkbox = card.querySelector(".mod-checkbox");
      if (checkbox) checkbox.checked = state.selectedModIds.has(mod.id);
      scroll.appendChild(card);
      observeModThumbnail(mod, card);
      return;
    }
    const card = document.createElement("div");
    card.className = "mod-card" + (state.settings.show_type_badge ? " show-type-badge" : "") + (state.detailsModId === mod.id ? " selected" : "") + (state.selectedModIds.has(mod.id) ? " selection-selected" : "") + (state.focusedModId === mod.id ? " keyboard-focused" : "") + (conflictInfo ? " has-conflict" : "");
    card.dataset.id = mod.id;

    const cardIconUrl = state.activeCharacter
      ? (mod.skin_icon_url || mod.hero_icon_url)
      : mod.hero_icon_url;
    const avatarBg = cardIconUrl ? `style="background-image:url('${cardIconUrl}')"` : "";
    const coverBg = mod.image_url ? `style="background-image:url('${mod.image_url}')"` : "";
    const initials = mod.character ? mod.character.slice(0, 2).toUpperCase() : "??";
    const typeBadges = state.settings.show_type_badge
      ? `<div class="mod-type-badges">${modTypes(mod).map((type) => `<span class="mod-type-badge ${modTypeClass(type)}">${escapeHtml(type)}</span>`).join("")}</div>`
      : "";
    card.innerHTML = `
      <input type="checkbox" class="mod-checkbox" ${state.selectedModIds.has(mod.id) ? "checked" : ""} />
      <div class="mod-cover ${mod.image_url ? "has-cover" : "no-cover"}" ${coverBg}>${mod.image_url ? "" : "▧"}</div>
      <div class="mod-avatar" ${avatarBg}>${cardIconUrl ? "" : initials}</div>
      <div class="mod-name-block">
        <div class="mod-name">${escapeHtml(displayModName(mod.name))}</div>
        ${mod.tags.map((t) => `<span class="mod-tag">${t} <span class="remove-tag" data-tag="${t}">✕</span></span>`).join("")}
      </div>
      ${typeBadges}
      <div class="mod-size" title="Tamanho total${mod.catalog_size_mb !== mod.size_mb ? " com complementos" : ""}: ${formatModSize(mod.catalog_size_mb ?? mod.size_mb)}">${formatModSize(mod.catalog_size_mb ?? mod.size_mb)}</div>
      <div class="switch ${mod.enabled ? "on" : ""}"><div class="knob"></div></div>
      ${conflictInfo ? `<button class="mod-conflict-alert" title="${conflictInfo.count} conflito(s) detectado(s)">⚠</button>` : ""}
      <button class="icon-btn remove-mod-btn" title="Remover mod (preserva imagens e ZIP/RAR/7z)">🗑</button>
      <button class="icon-btn permanent-delete-btn" title="Excluir permanentemente (apaga tudo)">×</button>
    `;

    card.querySelector(".switch").onclick = async () => {
      const res = await api().toggle_mod(mod.id);
      if (res.ok) {
        mod.enabled = res.enabled;
        renderLocalChange();
      } else if (res.error) {
        alert(res.error);
      }
    };

    card.querySelector(".mod-checkbox").onclick = (event) => {
      event.stopPropagation();
      selectMod(mod, event, { toggle: !event.shiftKey });
    };

    card.querySelector(".mod-conflict-alert")?.addEventListener("click", (event) => {
      event.stopPropagation();
      showModConflictDetails(mod, conflictInfo);
    });

    card.querySelectorAll(".remove-tag").forEach((x) => {
      x.onclick = async (e) => {
        e.stopPropagation();
        mod.tags = await api().remove_tag(mod.id, x.dataset.tag);
        renderLocalChange();
      };
    });

    card.querySelector(".remove-mod-btn").onclick = () => openModRemovalDialog(mod);
    card.querySelector(".permanent-delete-btn").onclick = () => openModRemovalDialog(mod, { permanent: true });

    card.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      openContextMenu(e.clientX, e.clientY, mod);
    });

    card.addEventListener("click", (e) => {
      if (e.target.closest("button, .switch, .remove-tag, input")) return;
      // Com uma seleção existente, a capa (a área acima do nome na grade) vira
      // uma zona de seleção. O nome e o restante do cartão continuam abrindo detalhes.
      if (state.selectedModIds.size && e.target.closest(".mod-cover, .mod-avatar")) {
        // Um segundo clique no mesmo cartão remove-o da seleção; Shift mantém
        // a seleção por intervalo.
        selectMod(mod, e, { toggle: !e.shiftKey });
        return;
      }

      if (state.settings.auto_open_details === false) {
        selectMod(mod, e, { toggle: !e.shiftKey });
        return;
      }
      state.keyboardNavigation = false;
      showModDetailsPage(mod.id);
    });

      scroll.appendChild(card);
      observeModThumbnail(mod, card);
      cardCache.set(mod.id, {card, signature: cardSignature});
    });
    if (end < rows.length) requestAnimationFrame(() => appendChunk(end));
  };
  appendChunk();
  renderBulkActions();
}

function renderHeaderCount() {
  const total = state.mods.length;
  const enabled = state.mods.filter((m) => m.enabled).length;
  document.getElementById("mods-header-count").textContent = `(${enabled}/${total} ativos)`;
}

// ---------------------------------------------------------
// Menu de contexto
// ---------------------------------------------------------
const ctxMenu = document.getElementById("ctx-menu");

async function refreshTagCatalog() {
  state.tags = await api().get_tags();
  renderTags();
}

function openCreateTagDialog(onCreated) {
  document.getElementById("create-tag-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "create-tag-overlay";
  overlay.className = "tag-create-overlay";
  overlay.innerHTML = `<div class="tag-create-dialog" role="dialog" aria-modal="true"><div class="tag-create-title"><span>🏷</span><b>Criar tag</b></div><input id="create-tag-name" maxlength="48" autocomplete="off" autofocus><div class="tag-create-actions"><button id="create-tag-cancel">Cancelar</button><button id="create-tag-confirm">Criar</button></div></div>`;
  document.body.appendChild(overlay);
  const input = overlay.querySelector("#create-tag-name");
  const close = () => overlay.remove();
  const submit = async () => {
    const result = await api().create_tag(input.value);
    if (!result.ok) return alert(result.error || "Não foi possível criar a tag.");
    state.tags = result.tags || await api().get_tags();
    renderTags();
    close();
    if (onCreated) await onCreated(result.tag);
  };
  overlay.querySelector("#create-tag-cancel").onclick = close;
  overlay.querySelector("#create-tag-confirm").onclick = submit;
  input.onkeydown = (event) => { if (event.key === "Enter") submit(); if (event.key === "Escape") { event.stopPropagation(); close(); } };
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  setTimeout(() => input.focus(), 0);
}

async function openIdentityCorrectionDialog(mod) {
  document.getElementById("identity-correction-overlay")?.remove();
  const roster = await api().get_character_roster();
  const overlay = document.createElement("div");
  overlay.id = "identity-correction-overlay";
  overlay.className = "tag-create-overlay identity-correction-overlay";
  overlay.innerHTML = `
    <div class="identity-correction-dialog" role="dialog" aria-modal="true" aria-label="Corrigir classificação do mod">
      <header><div><b>Corrigir classificação</b><small>Esta escolha manual não será alterada pelo próximo scan.</small></div><button type="button" class="identity-close" title="Fechar">×</button></header>
      <div class="identity-correction-body">
        <label>Personagem</label>
        <input id="identity-character-input" autocomplete="off" value="${escapeHtml(mod.character || "Generic")}" placeholder="Digite ou escolha um personagem">
        <div class="identity-hint">Digite um nome ou selecione na lista.</div>
        <div class="identity-option-list" id="identity-character-list"></div>
        <label>Skin</label>
        <input id="identity-skin-input" autocomplete="off" value="${escapeHtml(mod.skin || "Default")}" placeholder="Digite ou escolha uma skin">
        <div class="identity-hint">Você também pode escrever uma skin personalizada.</div>
        <div class="identity-option-list identity-skin-list" id="identity-skin-list"></div>
      </div>
      <footer><button type="button" class="identity-cancel">Cancelar</button><button type="button" class="identity-save">Salvar correção</button></footer>
    </div>`;
  document.body.appendChild(overlay);

  const characterInput = overlay.querySelector("#identity-character-input");
  const skinInput = overlay.querySelector("#identity-skin-input");
  const characterList = overlay.querySelector("#identity-character-list");
  const skinList = overlay.querySelector("#identity-skin-list");
  let knownSkins = [];
  const close = () => overlay.remove();
  const currentCharacter = () => characterInput.value.trim();

  const renderCharacters = () => {
    const query = currentCharacter().toLocaleLowerCase();
    const options = ["Generic", ...roster].filter((name) => !query || name.toLocaleLowerCase().includes(query));
    characterList.innerHTML = options.map((name) => `<button type="button" data-character="${encodeURIComponent(name)}" class="${name === currentCharacter() ? "selected" : ""}">${escapeHtml(name)}</button>`).join("") || `<span>Nenhum personagem encontrado.</span>`;
    characterList.querySelectorAll("[data-character]").forEach((button) => button.onclick = async () => {
      characterInput.value = decodeURIComponent(button.dataset.character);
      renderCharacters();
      await loadSkins();
    });
  };
  const renderSkins = () => {
    const query = skinInput.value.trim().toLocaleLowerCase();
    const options = knownSkins.filter((name) => !query || name.toLocaleLowerCase().includes(query));
    skinList.innerHTML = options.map((name) => `<button type="button" data-skin="${encodeURIComponent(name)}" class="${name === skinInput.value.trim() ? "selected" : ""}">${escapeHtml(name)}</button>`).join("") || `<span>${currentCharacter() === "Generic" ? "Mods genéricos não usam skin." : "Nenhuma skin correspondente; você pode manter o texto digitado."}</span>`;
    skinList.querySelectorAll("[data-skin]").forEach((button) => button.onclick = () => {
      skinInput.value = decodeURIComponent(button.dataset.skin);
      renderSkins();
    });
  };
  const loadSkins = async () => {
    const character = currentCharacter();
    knownSkins = character && character !== "Generic"
      ? (await api().get_character_skins(character)).map((entry) => entry.name)
      : [];
    if (character === "Generic") skinInput.value = "";
    renderSkins();
  };
  characterInput.oninput = () => renderCharacters();
  characterInput.onchange = loadSkins;
  skinInput.oninput = renderSkins;
  renderCharacters();
  await loadSkins();

  overlay.querySelector(".identity-close").onclick = close;
  overlay.querySelector(".identity-cancel").onclick = close;
  overlay.querySelector(".identity-save").onclick = async () => {
    const character = currentCharacter() || "Generic";
    if (character !== "Generic" && !roster.includes(character)) {
      return alert("Personagem inválido. Escolha um item da lista ou use Generic.");
    }
    const button = overlay.querySelector(".identity-save");
    button.disabled = true;
    const result = await api().set_mod_identity(mod.id, character, skinInput.value.trim() || "Default");
    button.disabled = false;
    if (!result || !result.ok) return alert(result?.error || "Não foi possível corrigir a classificação.");
    close();
    await loadData();
    await showModDetailsPage(mod.id);
  };
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  document.addEventListener("keydown", function onKey(event) {
    if (event.key !== "Escape" || !document.body.contains(overlay)) return;
    document.removeEventListener("keydown", onKey);
    close();
  });
  setTimeout(() => characterInput.select(), 0);
}

function openAssignTagMenu(anchor, mod, onAssigned) {
  document.getElementById("assign-tag-menu")?.remove();
  const menu = document.createElement("div");
  menu.id = "assign-tag-menu";
  menu.className = "assign-tag-menu";
  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${rect.left}px`;
  menu.style.top = `${rect.bottom + 5}px`;
  menu.innerHTML = `<button data-action="new">+ Nova tag…</button>${state.tags.map((tag) => `<button class="catalog-option" data-tag="${encodeURIComponent(tag.name)}" ${mod.tags.includes(tag.name) ? "disabled" : ""}><span>${escapeHtml(tag.name)}${mod.tags.includes(tag.name) ? " ✓" : ""}</span><span class="catalog-remove" data-action="delete-tag-catalog" data-value="${encodeURIComponent(tag.name)}" title="Excluir tag">×</span></button>`).join("")}`;
  document.body.appendChild(menu);
  const close = () => menu.remove();
  const assign = async (tag) => {
    const tags = await api().add_tag(mod.id, tag);
    if (Array.isArray(tags)) {
      mod.tags = tags;
      await refreshTagCatalog();
      close();
      if (onAssigned) await onAssigned();
    }
  };
  menu.querySelector('[data-action="new"]').onclick = () => {
    close();
    openCreateTagDialog(assign);
  };
  menu.querySelectorAll('[data-action="delete-tag-catalog"]').forEach((button) => button.onclick = async (event) => {
    event.stopPropagation();
    const tag = decodeURIComponent(button.dataset.value);
    if (!confirm(`Excluir a tag "${tag}" de todos os mods?`)) return;
    const result = await api().delete_tag_catalog(tag);
    if (!result.ok) return alert(result.error || "Não foi possível excluir a tag.");
    state.tags = result.tags || [];
    state.mods.forEach((item) => { item.tags = (item.tags || []).filter((value) => value !== tag); });
    close();
    renderLocalChange();
    await showModDetailsPage(mod.id);
  });
  menu.querySelectorAll("[data-tag]").forEach((button) => button.onclick = () => assign(decodeURIComponent(button.dataset.tag)));
  setTimeout(() => document.addEventListener("click", (event) => { if (!menu.contains(event.target) && event.target !== anchor) close(); }, { once: true }), 0);
}

function openCreateComponentLabelDialog(onCreated) {
  document.getElementById("create-component-label-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "create-component-label-overlay";
  overlay.className = "tag-create-overlay";
  overlay.innerHTML = `<div class="tag-create-dialog" role="dialog" aria-modal="true"><div class="tag-create-title"><span>≡</span><b>Criar rótulo de componente</b></div><input id="create-component-label-name" maxlength="80" autocomplete="off" autofocus><div class="tag-create-actions"><button id="create-component-label-cancel">Cancelar</button><button id="create-component-label-confirm">Criar</button></div></div>`;
  document.body.appendChild(overlay);
  const input = overlay.querySelector("#create-component-label-name");
  const close = () => overlay.remove();
  const submit = async () => {
    const result = await api().create_component_label(input.value);
    if (!result.ok) return alert(result.error || "Não foi possível criar o rótulo.");
    close();
    if (onCreated) await onCreated(result.label);
  };
  overlay.querySelector("#create-component-label-cancel").onclick = close;
  overlay.querySelector("#create-component-label-confirm").onclick = submit;
  input.onkeydown = (event) => { if (event.key === "Enter") submit(); if (event.key === "Escape") { event.stopPropagation(); close(); } };
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  setTimeout(() => input.focus(), 0);
}

async function openComponentLabelMenu(anchor, mod, componentIds, currentDescription) {
  const ids = Array.isArray(componentIds) ? componentIds : [componentIds];
  document.getElementById("component-label-menu")?.remove();
  const menu = document.createElement("div");
  menu.id = "component-label-menu";
  menu.className = "assign-tag-menu";
  const rect = anchor.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - 210))}px`;
  menu.style.top = `${Math.max(8, Math.min(rect.bottom + 5, window.innerHeight - 230))}px`;

  const renderLabels = (labels) => {
    const known = [...new Set(["Principal", "Acompanhamento", ...(Array.isArray(labels) ? labels : [])])];
    menu.innerHTML = `<button data-action="new">+ New label...</button><button data-label="">Automatic</button>${known.map((label) => {
      const removable = !["principal", "acompanhamento"].includes(label.toLocaleLowerCase());
      return `<button class="catalog-option" data-label="${encodeURIComponent(label)}" ${label === currentDescription ? "disabled" : ""}><span>${escapeHtml(label)}${label === currentDescription ? " ✓" : ""}</span>${removable ? `<span class="catalog-remove" data-action="delete-component-label" data-value="${encodeURIComponent(label)}" title="Excluir rótulo">×</span>` : ""}</button>`;
    }).join("")}`;
    bindMenuActions();
  };

  document.body.appendChild(menu);
  const close = () => menu.remove();
  const setLabel = async (label) => {
    const result = await api().set_components_description(mod.id, ids, label);
    if (!result.ok) return alert(result.error || "Não foi possível alterar o rótulo.");
    close();
    await showModDetailsPage(mod.id);
  };
  const bindMenuActions = () => {
    menu.querySelector('[data-action="new"]').onclick = () => {
      close();
      openCreateComponentLabelDialog(setLabel);
    };
    menu.querySelectorAll('[data-action="delete-component-label"]').forEach((button) => button.onclick = async (event) => {
      event.stopPropagation();
      const label = decodeURIComponent(button.dataset.value);
      if (!confirm(`Excluir o rótulo "${label}" dos componentes que o usam?`)) return;
      const result = await api().delete_component_label(label);
      if (!result.ok) return alert(result.error || "Não foi possível excluir o rótulo.");
      close();
      await showModDetailsPage(mod.id);
    });
    menu.querySelectorAll("[data-label]").forEach((button) => button.onclick = () => setLabel(decodeURIComponent(button.dataset.label)));
  };
  // Mostra uma versão funcional imediatamente. O catálogo completo é
  // preenchido depois, sem transformar um atraso do backend em clique morto.
  renderLabels([]);
  try {
    const labels = await api().get_component_labels();
    if (document.body.contains(menu)) renderLabels(labels);
  } catch (error) {
    console.warn("Não foi possível carregar o catálogo de labels:", error);
  }
  menu.addEventListener("click", (event) => event.stopPropagation());
  setTimeout(() => document.addEventListener("click", (event) => { if (!menu.contains(event.target) && event.target !== anchor) close(); }, { once: true }), 0);
}

function openContextMenu(x, y, mod) {
  state.ctxMod = mod;
  ctxMenu.innerHTML = `<div class="ctx-item ctx-parent">Adicionar tag… <span>›</span><div class="ctx-submenu"><button class="ctx-submenu-item" data-action="create-tag">+ Nova tag…</button>${state.tags.map(t => `<button class="ctx-submenu-item catalog-option" data-action="quick-tag" data-value="${encodeURIComponent(t.name)}"><span>${escapeHtml(t.name)}</span><span class="catalog-remove" data-action="delete-tag-catalog" data-value="${encodeURIComponent(t.name)}" title="Excluir tag">×</span></button>`).join("")}</div></div>
    <div class="ctx-item" data-action="move-to">Mover para…</div>
    <div class="ctx-sep"></div><div class="ctx-item" data-action="rename">Renomear</div><div class="ctx-item" data-action="edit-image">Editar imagem</div><div class="ctx-item" data-action="open-folder">Abrir no Explorador</div><div class="ctx-sep"></div><div class="ctx-item" data-action="remove">Remover mod</div><div class="ctx-item danger" data-action="delete-permanently">Excluir permanentemente</div>`;
  ctxMenu.style.left = x + "px";
  ctxMenu.style.top = y + "px";
  ctxMenu.classList.add("open");
}

function escapeHtml(value) { const node = document.createElement("span"); node.textContent = value || ""; return node.innerHTML; }

document.addEventListener("click", () => ctxMenu.classList.remove("open"));

ctxMenu.addEventListener("click", async (e) => {
    const item = e.target.closest("[data-action], .ctx-submenu-item, .ctx-item");
    if (!item) return;
    e.stopPropagation();
    const action = item.dataset.action;
    const mod = state.ctxMod;
    if (!action) return;
    ctxMenu.classList.remove("open");
    if (!mod) return;

    if (action === "rename") {
      await renameModPrompt(mod);
    } else if (action === "create-tag") {
      openCreateTagDialog(async (tag) => {
        const tags = await api().add_tag(mod.id, tag);
        if (Array.isArray(tags)) { mod.tags = tags; await refreshTagCatalog(); renderLocalChange(); }
      });
    } else if (action === "quick-tag") {
      const tags = await api().add_tag(mod.id, decodeURIComponent(item.dataset.value));
      if (Array.isArray(tags)) { mod.tags = tags; renderLocalChange(); }
    } else if (action === "delete-tag-catalog") {
      const tag = decodeURIComponent(item.dataset.value);
      if (!confirm(`Excluir a tag "${tag}" de todos os mods?`)) return;
      const result = await api().delete_tag_catalog(tag);
      if (!result.ok) return alert(result.error || "Não foi possível excluir a tag.");
      state.tags = result.tags || [];
      state.mods.forEach((entry) => { entry.tags = (entry.tags || []).filter((value) => value !== tag); });
      renderLocalChange();
    } else if (action === "move-to") {
      const result = await api().choose_move_destination(mod.id);
      if (result?.ok) {
        await reloadAll();
      } else if (!result?.cancelled) {
        alert(result?.error || "Não foi possível mover o mod.");
      }
    } else if (action === "edit-image") {
      const result = await api().edit_image_dialog(mod.id);
      if (result.ok) { await refreshModInState(mod.id); renderLocalChange(); }
      else if (!result.cancelled) alert(result.error || "Não foi possível alterar a capa.");
    } else if (action === "open-folder") {
      await api().open_mod_folder(mod.id);
    } else if (action === "copy-path") {
      try {
        await navigator.clipboard.writeText(mod.name);
      } catch (err) {
        console.warn("Clipboard indisponível:", err);
      }
    } else if (action === "remove") {
      openModRemovalDialog(mod);
    } else if (action === "delete-permanently") {
      openModRemovalDialog(mod, { permanent: true });
    } else if (action === "move-to" || action === "edit-image") {
      alert("Essa ação entra em uma próxima etapa.");
    }
});

function buildAssetTree(assetPaths) {
  const root = {};
  assetPaths.forEach((rawPath) => {
    const parts = String(rawPath).replaceAll("\\", "/").split("/").filter(Boolean);
    let branch = root;
    parts.forEach((part) => { branch[part] ||= {}; branch = branch[part]; });
  });
  const render = (node) => `<ul>${Object.entries(node).map(([name, children]) => {
    const isFile = Object.keys(children).length === 0;
    return `<li class="${isFile ? "asset-file" : "asset-folder"}"><span>${isFile ? "▱" : "▹"}</span>${escapeHtml(name)}${isFile ? "" : render(children)}</li>`;
  }).join("")}</ul>`;
  return render(root);
}

function galleryImageLabel(image) {
  return image.title || image.name.replace(/^image_\d+_/, "").replace(/\.[^.]+$/, "");
}

function isGalleryVideo(media) {
  return media.media_type === "video" || /\.(mp4|webm|ogv|mov)$/i.test(media.name || "");
}

function galleryPreview(media, className = "") {
  const label = escapeHtml(galleryImageLabel(media));
  const source = media.preview_url || media.url;
  return isGalleryVideo(media)
    ? (source
      ? `<video class="${className}" src="${source}" muted preload="metadata" aria-label="${label}"></video>`
      : `<div class="gallery-media-placeholder ${className}" aria-label="${label}">▶</div>`)
    : (source
      ? `<img class="${className}" src="${source}" alt="${label}" loading="lazy">`
      : `<div class="gallery-media-placeholder ${className}" aria-label="${label}">▧</div>`);
}

let activeGalleryViewer = null;

function closeGalleryViewer() {
  if (activeGalleryViewer?.close) activeGalleryViewer.close();
  else document.getElementById("gallery-viewer")?.remove();
}

async function openGalleryViewer(mod, startIndex) {
  let images = [...(mod.gallery_images || [])];
  if (!images.length) return;
  let current = Math.max(0, Math.min(startIndex, images.length - 1));
  let galleryOrderChanged = false;
  let ignoreThumbnailClick = false;
  let wheelDelta = 0;
  let wheelResetTimer = null;
  let wheelNavigationLocked = false;
  const viewer = document.createElement("div");
  viewer.id = "gallery-viewer";
  document.body.appendChild(viewer);
  const close = () => {
    document.removeEventListener("keydown", onViewerKeyDown);
    viewer.removeEventListener("wheel", onViewerWheel);
    if (wheelResetTimer) clearTimeout(wheelResetTimer);
    if (activeGalleryViewer?.element === viewer) activeGalleryViewer = null;
    viewer.remove();
    if (galleryOrderChanged && state.detailsModId === mod.id) {
      setTimeout(() => showModDetailsPage(mod.id), 0);
    }
  };
  const onViewerKeyDown = (event) => {
    if (!document.body.contains(viewer)) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (["ArrowLeft", "ArrowUp"].includes(event.key) && current > 0) {
      event.preventDefault();
      current -= 1;
      render();
    } else if (["ArrowRight", "ArrowDown"].includes(event.key) && current < images.length - 1) {
      event.preventDefault();
      current += 1;
      render();
    }
  };
  const onViewerWheel = (event) => {
    const thumbnailStrip = event.target.closest(".gallery-viewer-thumbnails");
    if (thumbnailStrip) {
      // A faixa inferior é horizontal; a roda comum também a percorre sem
      // exigir Shift, mantendo a galeria confortável com muitas mídias.
      event.preventDefault();
      thumbnailStrip.scrollLeft += event.deltaY || event.deltaX;
      return;
    }
    if (event.target.closest(".gallery-viewer-top") || wheelNavigationLocked) return;
    const delta = event.deltaY || event.deltaX;
    if (!delta) return;
    event.preventDefault();
    wheelDelta += delta;
    if (wheelResetTimer) clearTimeout(wheelResetTimer);
    wheelResetTimer = setTimeout(() => { wheelDelta = 0; }, 140);
    if (Math.abs(wheelDelta) < 36) return;

    const direction = wheelDelta > 0 ? 1 : -1;
    const nextIndex = current + direction;
    wheelDelta = 0;
    if (nextIndex < 0 || nextIndex >= images.length) return;
    wheelNavigationLocked = true;
    current = nextIndex;
    Promise.resolve(render()).finally(() => { wheelNavigationLocked = false; });
  };
  activeGalleryViewer = { element: viewer, close };
  document.addEventListener("keydown", onViewerKeyDown);
  viewer.addEventListener("wheel", onViewerWheel, { passive: false });
  const render = async () => {
    const requestedIndex = current;
    let image = images[current];
    if (!image.url) {
      viewer.innerHTML = `<div class="gallery-viewer-top"><span>${current + 1} / ${images.length}</span><b>${escapeHtml(galleryImageLabel(image))}</b><button id="gallery-viewer-close" title="Fechar">×</button></div><div class="gallery-viewer-loading">Carregando mídia…</div>`;
      viewer.querySelector("#gallery-viewer-close").onclick = close;
      const result = await api().get_gallery_media(mod.id, image.name);
      if (!document.body.contains(viewer)) return;
      if (!result || !result.ok) {
        viewer.innerHTML += `<div class="gallery-viewer-error">${escapeHtml((result && result.error) || "Não foi possível carregar a mídia.")}</div>`;
        return;
      }
      image.url = result.url;
      if (current !== requestedIndex) return render();
    }
    const mainMedia = isGalleryVideo(image)
      ? `<video class="gallery-viewer-image" src="${image.url}" controls autoplay></video>`
      : `<img class="gallery-viewer-image" src="${image.url}" alt="${escapeHtml(galleryImageLabel(image))}">`;
    viewer.innerHTML = `<div class="gallery-viewer-top"><span>${current + 1} / ${images.length}</span><b>${escapeHtml(galleryImageLabel(image))}</b><button id="gallery-viewer-close" title="Fechar">×</button></div>
      <button class="gallery-nav previous" ${current === 0 ? "disabled" : ""}>‹</button>
      ${mainMedia}
      <button class="gallery-nav next" ${current === images.length - 1 ? "disabled" : ""}>›</button>
      <div class="gallery-viewer-thumbnails">${images.map((item, index) => `<button draggable="false" class="gallery-viewer-thumb ${index === current ? "active" : ""}" data-index="${index}" title="${escapeHtml(galleryImageLabel(item))} — Arraste para alterar a ordem">${galleryPreview(item)}</button>`).join("")}</div>`;
    viewer.querySelector("#gallery-viewer-close").onclick = close;
    viewer.querySelector(".previous").onclick = () => { current -= 1; render(); };
    viewer.querySelector(".next").onclick = () => { current += 1; render(); };
    viewer.querySelector(`.gallery-viewer-thumb[data-index="${current}"]`)?.scrollIntoView({ block: "nearest", inline: "center" });
    viewer.querySelectorAll(".gallery-viewer-thumb").forEach((button) => {
      button.onclick = () => {
        if (ignoreThumbnailClick) return;
        current = Number(button.dataset.index);
        render();
      };
      button.onmousedown = (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        const strip = button.parentElement;
        const startX = event.clientX;
        let moving = false;

        const moveThumbnail = (moveEvent) => {
          if (!moving && Math.abs(moveEvent.clientX - startX) < 5) return;
          moving = true;
          ignoreThumbnailClick = true;
          button.classList.add("dragging");
          const target = document.elementFromPoint(moveEvent.clientX, moveEvent.clientY)?.closest(".gallery-viewer-thumb");
          if (!target || target === button || target.parentElement !== strip) return;
          const targetBox = target.getBoundingClientRect();
          strip.insertBefore(button, moveEvent.clientX < targetBox.left + targetBox.width / 2 ? target : target.nextSibling);
        };

        const finishThumbnailDrag = async () => {
          document.removeEventListener("mousemove", moveThumbnail);
          document.removeEventListener("mouseup", finishThumbnailDrag);
          button.classList.remove("dragging");
          if (!moving) return;
          const reordered = [...strip.querySelectorAll(".gallery-viewer-thumb")].map((thumb) => images[Number(thumb.dataset.index)]);
          const orderChanged = reordered.some((media, index) => media !== images[index]);
          if (!orderChanged) {
            setTimeout(() => { ignoreThumbnailClick = false; }, 0);
            return;
          }
          const selectedMedia = images[current];
          const result = await api().reorder_detail_gallery(mod.id, reordered.map((media) => media.name));
          if (!result?.ok) {
            alert(result?.error || "Não foi possível alterar a ordem da galeria.");
            render();
            setTimeout(() => { ignoreThumbnailClick = false; }, 0);
            return;
          }
          images = reordered;
          mod.gallery_images = reordered;
          current = reordered.indexOf(selectedMedia);
          galleryOrderChanged = true;
          render();
          setTimeout(() => { ignoreThumbnailClick = false; }, 0);
        };
        document.addEventListener("mousemove", moveThumbnail);
        document.addEventListener("mouseup", finishThumbnailDrag, { once: true });
      };
      button.ondragstart = (event) => event.preventDefault();
    });
  };
  viewer.onclick = (event) => { if (event.target === viewer) close(); };
  await render();
}

function showGalleryImageMenu(event, mod, image) {
  event.preventDefault();
  document.getElementById("gallery-image-menu")?.remove();
  const menu = document.createElement("div");
  menu.id = "gallery-image-menu";
  menu.className = "gallery-image-menu";
  menu.style.left = `${event.clientX}px`;
  menu.style.top = `${event.clientY}px`;
  menu.innerHTML = `${isGalleryVideo(image) ? "" : `<button data-action="cover">Usar como capa</button>`}<button data-action="title">Renomear</button>`;
  document.body.appendChild(menu);
  const close = () => menu.remove();
  const coverAction = menu.querySelector('[data-action="cover"]');
  if (coverAction) coverAction.onclick = async () => {
    const result = await api().set_detail_cover(mod.id, image.name);
    close();
    if (result.ok) { await reloadAll(); await showModDetailsPage(mod.id); }
  };
  menu.querySelector('[data-action="title"]').onclick = async () => {
    const title = prompt("Nome personalizado da imagem:", image.title || "");
    if (title === null) return close();
    const result = await api().set_detail_image_title(mod.id, image.name, title);
    close();
    if (result.ok) await showModDetailsPage(mod.id);
  };
  setTimeout(() => document.addEventListener("click", close, { once: true }), 0);
}

// Os dados do detalhe não esperam a decodificação das imagens da galeria.
let detailRequestSerial = 0;
let pendingDetailRequest = null;
const detailPreviewCache = new Map();
const detailMetadataCache = new Map();
const detailPreviewQueue = [];
let detailPreviewWorkers = 0;
const DETAIL_PREVIEW_WORKER_LIMIT = 2;
const DETAIL_PREVIEW_CACHE_LIMIT = 48;
const DETAIL_METADATA_CACHE_LIMIT = 8;

function rememberDetailMetadata(mod) {
  if (!mod?.id) return;
  detailMetadataCache.delete(mod.id);
  detailMetadataCache.set(mod.id, mod);
  while (detailMetadataCache.size > DETAIL_METADATA_CACHE_LIMIT) {
    detailMetadataCache.delete(detailMetadataCache.keys().next().value);
  }
}

function isCurrentDetailRequest(modId, serial) {
  return state.detailsModId === modId && detailRequestSerial === serial;
}

function rememberDetailPreview(key, url) {
  if (!key || !url) return;
  detailPreviewCache.delete(key);
  detailPreviewCache.set(key, url);
  while (detailPreviewCache.size > DETAIL_PREVIEW_CACHE_LIMIT) {
    detailPreviewCache.delete(detailPreviewCache.keys().next().value);
  }
}

function restoreDetailPreviews(mod) {
  rememberDetailPreview(mod.thumbnail_key, mod.image_url);
  for (const media of mod.gallery_images || []) {
    if (isGalleryVideo(media)) continue;
    const cached = detailPreviewCache.get(media.thumbnail_key);
    if (cached) media.preview_url = cached;
  }
}

function applyDetailPreview(task, url) {
  if (!isCurrentDetailRequest(task.mod.id, task.serial)) return;
  const item = document.querySelector(`#mod-detail-content .detail-gallery-item[data-index="${task.index}"]`);
  const oldPreview = item?.querySelector("img, .gallery-media-placeholder");
  if (!oldPreview) return;
  if (!url) {
    oldPreview.setAttribute("aria-label", "Prévia indisponível; clique para abrir a mídia.");
    oldPreview.setAttribute("aria-busy", "false");
    return;
  }
  task.media.preview_url = url;
  const preview = document.createElement("img");
  preview.src = url;
  preview.alt = galleryImageLabel(task.media);
  preview.loading = "lazy";
  preview.onclick = () => openGalleryViewer(task.mod, task.index);
  oldPreview.replaceWith(preview);
}

function drainDetailPreviewQueue() {
  while (detailPreviewWorkers < DETAIL_PREVIEW_WORKER_LIMIT && detailPreviewQueue.length) {
    const task = detailPreviewQueue.shift();
    if (!isCurrentDetailRequest(task.mod.id, task.serial)) continue;
    const cached = detailPreviewCache.get(task.media.thumbnail_key);
    if (cached) {
      applyDetailPreview(task, cached);
      continue;
    }
    detailPreviewWorkers += 1;
    void (async () => {
      try {
        const result = await api().get_gallery_preview(task.mod.id, task.media.name);
        const valid = result?.ok && result.preview_url && result.thumbnail_key === task.media.thumbnail_key;
        if (valid) rememberDetailPreview(result.thumbnail_key, result.preview_url);
        applyDetailPreview(task, valid ? result.preview_url : null);
      } catch (_) {
        // Falha de miniatura não impede abrir a mídia original ou usar os controles.
        applyDetailPreview(task, null);
      } finally {
        detailPreviewWorkers -= 1;
        drainDetailPreviewQueue();
      }
    })();
  }
}

function loadDetailGalleryPreviews(mod, serial) {
  (mod.gallery_images || []).forEach((media, index) => {
    if (isGalleryVideo(media) || media.preview_url || media.url) return;
    detailPreviewQueue.push({ mod, media, index, serial });
  });
  drainDetailPreviewQueue();
}

const componentClassificationJobs = new Map();

function openComponentDialog(title, html) {
  document.getElementById("component-diagnostic-overlay")?.remove();
  const previousFocus = document.activeElement;
  const overlay = document.createElement("div");
  overlay.id = "component-diagnostic-overlay";
  overlay.className = "diagnostic-overlay";
  overlay.innerHTML = `<section class="diagnostic-dialog" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}" tabindex="-1"><h3>${escapeHtml(title)}</h3>${html}<p class="dialog-error" role="alert"></p><footer><button class="btn dialog-close">Fechar</button></footer></section>`;
  const panel = overlay.querySelector(".diagnostic-dialog");
  const close = () => { if (overlay.dataset.busy === "true") return; overlay.remove(); previousFocus?.focus(); };
  overlay.querySelector(".dialog-close").onclick = close;
  overlay.onclick = event => { if (event.target === overlay) close(); };
  overlay.onkeydown = event => {
    if (event.key === "Escape") { event.stopPropagation(); close(); }
    if (event.key === "Tab") {
      const controls = [...overlay.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex]:not([tabindex="-1"])')]
        .filter(control => !control.hidden && control.getClientRects().length > 0);
      const first = controls[0], last = controls.at(-1);
      if (!controls.length) { event.preventDefault(); panel.focus(); }
      else if (document.activeElement === panel || !overlay.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  };
  document.body.appendChild(overlay);
  (overlay.querySelector("button:not(:disabled), input:not(:disabled)") || panel).focus();
  return overlay;
}

async function showComponentDiagnosis(mod, component) {
  const result = await api().get_component_diagnosis(mod.id, component.id);
  if (!result?.ok) return alert(result?.error || "Não foi possível obter o diagnóstico.");
  const names = {missing:"Arquivos ausentes", pending:"Ainda não analisado", read_error:"Falha de leitura", unrecognized:"Tipo não reconhecido", analyzed:"Analisado"};
  const overlay = openComponentDialog("Por que esta classificação?", `<p><b>${escapeHtml(component.name)}</b></p><p>${names[result.status] || result.status} · ${result.asset_count} asset(s)</p><p>${escapeHtml(result.message)}</p>${result.evidence.map(e => `<details open><summary>${escapeHtml(e.type)} — ${escapeHtml(e.source)} (${e.count})</summary>${e.paths.map(path => `<code>${escapeHtml(path)}</code>`).join("")}</details>`).join("")}<p>Identidade pelos assets: ${escapeHtml(result.character || "Não identificada")} / ${escapeHtml(result.skin || "—")}</p>${result.identity_override ? `<p>Seleção salva no cadastro: ${escapeHtml(result.identity_override.character)} / ${escapeHtml(result.identity_override.skin)}. Ela é preservada pela análise.</p>` : ""}<button class="btn retry-analysis">Reanalisar este componente</button>`);
  overlay.querySelector(".retry-analysis").onclick = async event => {
    event.target.disabled = true;
    event.target.textContent = "Analisando…";
    try {
      const response = await api().retry_component_analysis(mod.id, component.id);
      if (!response?.ok) throw new Error(response?.error || "Falha na análise.");
      await refreshModInState(mod.id);
      renderLocalChange();
      if (state.detailsModId === mod.id) await showModDetailsPage(mod.id, {onlyIfOpen:true});
      if (overlay.isConnected) await showComponentDiagnosis(mod, component);
    } catch (error) {
      overlay.querySelector(".dialog-error").textContent = error.message;
      event.target.disabled = false;
    }
  };
}

function showComponentRules(mod, component) {
  const others = mod.components.filter(c => c.id !== component.id);
  const overlay = openComponentDialog("Relações do componente", `<p>${escapeHtml(component.name)}</p><label>Grupo de alternativas<input type="text" class="exclusive-group" maxlength="80" value="${escapeHtml(component.exclusive_group || "")}" placeholder="Ex.: roupa principal"></label><p>Use o mesmo grupo em variações que não devem ficar ativas juntas. Deixe vazio para um componente independente.</p><fieldset><legend>Depende destes componentes</legend>${others.map(c => `<label><input type="checkbox" class="component-requirement" value="${c.id}" ${(component.requires || []).includes(c.id) ? "checked" : ""}> ${escapeHtml(c.name)}</label>`).join("") || "Nenhum outro componente."}</fieldset><p>Ativar um complemento ativa seus requisitos; desativar um requisito desativa seus dependentes. Salvar aplica essas regras ao estado atual.</p><button class="btn primary save-rules">Salvar relações</button>`);
  const suggestions = document.createElement("button");
  suggestions.className = "btn component-suggestions";
  suggestions.textContent = "Ver sugestões de relações";
  suggestions.onclick = () => void showRelationSuggestions(mod, component.id);
  overlay.querySelector(".save-rules").before(suggestions);
  overlay.querySelector(".save-rules").onclick = async event => {
    event.target.disabled = true;
    try {
      const result = await api().set_component_rules(mod.id, component.id,
        overlay.querySelector(".exclusive-group").value,
        [...overlay.querySelectorAll(".component-requirement:checked")].map(input => input.value));
      if (!result?.ok) throw new Error(result?.error || "Não foi possível salvar as relações.");
      overlay.remove();
      await refreshModInState(mod.id);
      renderLocalChange();
      if (state.detailsModId === mod.id) await showModDetailsPage(mod.id, {onlyIfOpen:true});
    } catch (error) {
      overlay.querySelector(".dialog-error").textContent = error.message;
      event.target.disabled = false;
    }
  };
}

function completeComponentClassification(mod) {
  if (!mod.component_classification_pending || componentClassificationJobs.has(mod.id)) return;
  const job = (async () => {
    try {
      const result = await api().classify_mod_components(mod.id);
      if (!result?.ok) throw new Error(result?.error || "Falha ao classificar componentes.");
      if (!result.changed) return;
      const fresh = await refreshModInState(mod.id);
      renderLocalChange();
      if (fresh && state.detailsModId === mod.id) {
        const content = document.getElementById("mod-detail-content");
        const scrollTop = content?.scrollTop || 0;
        await showModDetailsPage(mod.id, { onlyIfOpen: true });
        if (state.detailsModId === mod.id && content) content.scrollTop = scrollTop;
      }
    } catch (error) {
      console.error("Não foi possível classificar os componentes:", error);
      const status = document.getElementById("component-classification-status");
      if (state.detailsModId === mod.id && status) status.textContent = "Não foi possível concluir a análise. Reabra os detalhes para tentar novamente.";
    } finally {
      componentClassificationJobs.delete(mod.id);
      const status = document.getElementById("component-classification-status");
      if (state.detailsModId === mod.id && status?.textContent === "Analisando componentes…") {
        status.textContent = "Análise concluída. Sem assets legíveis, a classificação anterior é mantida.";
      }
    }
  })();
  componentClassificationJobs.set(mod.id, job);
}

async function showModDetailsPage(modId, { onlyIfOpen = false } = {}) {
  if (onlyIfOpen && state.detailsModId !== modId) return;
  if (pendingDetailRequest?.modId === modId && pendingDetailRequest.opening && state.detailsModId === modId) {
    return pendingDetailRequest.promise;
  }
  const visibleCinematicSections = document.querySelectorAll("#mod-detail-content details[data-cinematic-section]");
  if (state.detailsModId === modId && visibleCinematicSections.length) {
    const sectionStates = state.cinematicSectionStates.get(modId) || new Map();
    visibleCinematicSections.forEach((section) => sectionStates.set(section.dataset.cinematicSection, section.open));
    state.cinematicSectionStates.set(modId, sectionStates);
  }
  const overlay = document.getElementById("mod-detail-overlay");
  const content = document.getElementById("mod-detail-content");
  const switching = state.detailsModId !== modId || !overlay.classList.contains("open");
  if (switching) {
    state.cinematicPreviewIndex = 0;
    state.detailContentsExpanded = false;
    state.selectedComponentIds.clear();
    state.lastSelectedComponentId = null;
    state.activeComponentContentId = null;
    state.componentContent = null;
  }
  state.detailsModId = modId;
  const serial = ++detailRequestSerial;
  detailPreviewQueue.length = 0;
  document.getElementById("details-panel").classList.remove("open");
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  content.setAttribute("aria-busy", "true");
  if (switching) {
    const cachedMod = state.mods.find(item => item.id === modId);
    content.innerHTML = `<h1>${escapeHtml(displayModName(cachedMod?.name || "Detalhes do mod"))}</h1><p class="detail-load-status" role="status">Carregando detalhes…</p>`;
    content.scrollTop = 0;
  }
  const cachedDetails = switching ? detailMetadataCache.get(modId) : null;
  if (cachedDetails) {
    restoreDetailPreviews(cachedDetails);
    renderModDetailsPage(cachedDetails, serial);
    content.setAttribute("aria-busy", "false");
    return;
  }
  const request = { modId, serial, opening: switching, promise: null };
  pendingDetailRequest = request;
  request.promise = (async () => {
    try {
      const mod = await api().get_mod_details(modId, false);
      if (!isCurrentDetailRequest(modId, serial)) return;
      if (!mod || mod.ok === false) throw new Error(mod?.error || "Este mod não está mais disponível na biblioteca.");
      preserveModThumbnail(mod, state.mods.find(item => item.id === modId));
      restoreDetailPreviews(mod);
      rememberDetailMetadata(mod);
      renderModDetailsPage(mod, serial);
    } catch (error) {
      if (!isCurrentDetailRequest(modId, serial)) return;
      content.innerHTML = `<h1>Detalhes do mod</h1><p class="detail-load-status" role="alert">${escapeHtml(error.message || "Não foi possível carregar os detalhes.")}</p><button class="btn-secondary" id="retry-mod-details">Tentar novamente</button>`;
      document.getElementById("retry-mod-details").onclick = () => showModDetailsPage(modId);
    } finally {
      if (isCurrentDetailRequest(modId, serial)) content.setAttribute("aria-busy", "false");
      if (pendingDetailRequest === request) pendingDetailRequest = null;
    }
  })();
  return request.promise;
}

function componentOriginSummary(component) {
  const sizeBytes = Number(component.size_bytes || (component.files || []).reduce((sum, entry) => sum + Number(entry.size || 0), 0));
  const english = window.getUiLanguage?.() === "en";
  const source = component.source_archive || (english ? "Source not recorded" : "Origem não registrada");
  const hash = component.content_sha256 || component.files?.find(entry => entry.sha256)?.sha256 || "";
  const dateValue = component.updated_at || component.added_at || "";
  const date = dateValue ? new Date(dateValue).toLocaleString(english ? "en-US" : "pt-BR") : (english ? "date not recorded" : "data não registrada");
  const status = component.updated_at ? (english ? "Updated" : "Atualizado") : (english ? "Added" : "Adicionado");
  const missingHash = english ? "Hash not recorded" : "Hash não registrado";
  return `<small class="component-origin" title="${escapeHtml(source)} · ${escapeHtml(hash || missingHash)}">${status} ${escapeHtml(date)} · ${escapeHtml(formatModSize(sizeBytes / 1048576))} · ${escapeHtml(source)}${hash ? ` · SHA ${escapeHtml(hash.slice(0, 10))}…` : ""}</small>`;
}

async function recordImportTiming(sample) {
  try { await api().record_import_performance(sample); }
  catch (_) { /* O diagnóstico não pode transformar uma importação concluída em erro. */ }
}

async function finishComponentImport(result, modId, targetComponentId = null, startedAt = (globalThis.performance?.now?.() ?? Date.now())) {
  if (!result?.ok) throw new Error(result?.error || "Não foi possível adicionar os componentes.");
  const record = result.record || {};
  const suggestions = record.suggested_updates || [];
  let updated = 0;
  for (const suggestion of suggestions) {
    const apply = targetComponentId || confirm(
      `O novo pacote parece ser uma atualização de “${suggestion.target_name}”.\n\n${suggestion.reason}\n\n` +
      "OK: substituir o conteúdo atual e guardar a versão anterior no histórico.\n" +
      "Cancelar: manter o pacote como uma nova variante desativada."
    );
    if (!apply) continue;
    const response = await api().promote_added_component_to_update(
      modId, suggestion.new_component_id, suggestion.target_component_id,
    );
    if (!response?.ok) throw new Error(response?.error || "Não foi possível aplicar a atualização sugerida.");
    updated += 1;
  }
  const reloadStarted = globalThis.performance?.now?.() ?? Date.now();
  await reloadAll();
  const reloadFinished = globalThis.performance?.now?.() ?? Date.now();
  await showModDetailsPage(modId);
  const finishedAt = globalThis.performance?.now?.() ?? Date.now();
  void recordImportTiming({
    kind: targetComponentId ? "component_update" : "component_append",
    mod_id: modId,
    commit_ms: reloadStarted - startedAt,
    reload_ms: reloadFinished - reloadStarted,
    detail_ms: finishedAt - reloadFinished,
    total_ms: finishedAt - startedAt,
    backend_ms: result.backend_ms || 0,
  });
  const added = Math.max(0, Number(record.added_components || 0) - updated);
  const skipped = Number(record.skipped_duplicates || 0);
  alert(`${updated ? `${updated} componente(s) atualizado(s); ` : ""}${added} nova(s) variante(s) adicionada(s) desativada(s).${skipped ? ` ${skipped} duplicata(s) foram ignoradas.` : ""}`);
}

async function importComponentsIntoMod(mod, { filepaths = null, targetComponentId = null, button = null } = {}) {
  if (pendingOperation()) { await resumeLastOperation(); return; }
  if (button) button.disabled = true;
  const startedAt = globalThis.performance?.now?.() ?? Date.now();
  try {
    const requestId = newOperationRequest(targetComponentId ? "component-update" : "component-append");
    const descriptor = {
      requestId,
      title: targetComponentId ? "Atualizando componente" : "Adicionando componentes",
      context: { kind: "component_append", mod_id: mod.id, target_component_id: targetComponentId },
    };
    const result = await runImportOperation(
      () => api().start_add_mod_components(mod.id, requestId, filepaths, targetComponentId),
      descriptor.title,
      descriptor,
    );
    if (!result || result.cancelled) return;
    await finishComponentImport(result, mod.id, targetComponentId, startedAt);
  } catch (error) {
    alert(error.message || "Não foi possível adicionar os componentes.");
  } finally {
    if (button?.isConnected) button.disabled = false;
  }
}

function openComponentHistory(mod, component) {
  const versions = component.versions || [];
  const overlay = openComponentDialog(
    "Histórico do componente",
    `<p><b>${escapeHtml(component.name)}</b></p><p>A versão atual permanece ativa até você escolher restaurar outra.</p>` +
    `<div class="component-version-list">${versions.map((version) => {
      const when = version.saved_at ? new Date(version.saved_at).toLocaleString("pt-BR") : "data não registrada";
      const size = formatModSize(Number(version.size_bytes || 0) / 1048576);
      return `<article><div><b>${escapeHtml(when)}</b><small>${escapeHtml(version.source_archive || "Origem não registrada")} · ${escapeHtml(size)}</small></div><button class="btn restore-component-version" data-version-id="${escapeHtml(version.id)}">Restaurar</button></article>`;
    }).join("") || '<p class="maintenance-empty">Ainda não há versões anteriores deste componente.</p>'}</div>`,
  );
  overlay.querySelectorAll(".restore-component-version").forEach((button) => button.onclick = async () => {
    if (!confirm("Restaurar esta versão? A versão atual será guardada no histórico.")) return;
    overlay.dataset.busy = "true"; button.disabled = true;
    try {
      const result = await api().restore_component_version(mod.id, component.id, button.dataset.versionId);
      if (!result?.ok) throw new Error(result?.error || "Não foi possível restaurar a versão.");
      overlay.remove(); await reloadAll(); await showModDetailsPage(mod.id);
    } catch (error) { overlay.querySelector(".dialog-error").textContent = error.message; button.disabled = false; }
    finally { overlay.dataset.busy = "false"; }
  });
}

function openRemovedComponents(mod) {
  const removed = mod.removed_components || [];
  const overlay = openComponentDialog(
    "Componentes removidos",
    `<p>Os arquivos continuam guardados na biblioteca privada e podem ser restaurados.</p><div class="component-version-list">${removed.map((entry) => `<article><div><b>${escapeHtml(entry.component?.name || "Componente")}</b><small>Removido em ${escapeHtml(entry.removed_at ? new Date(entry.removed_at).toLocaleString(window.getUiLanguage?.() === "en" ? "en-US" : "pt-BR") : "data não registrada")}</small></div><button class="btn restore-removed-component" data-removed-id="${escapeHtml(entry.id)}">Restaurar</button></article>`).join("") || '<p class="maintenance-empty">Nenhum componente removido.</p>'}</div>`,
  );
  overlay.querySelectorAll(".restore-removed-component").forEach((button) => button.onclick = async () => {
    overlay.dataset.busy = "true"; button.disabled = true;
    try {
      const result = await api().restore_removed_component(mod.id, button.dataset.removedId);
      if (!result?.ok) throw new Error(result?.error || "Não foi possível restaurar o componente.");
      overlay.remove(); await reloadAll(); await showModDetailsPage(mod.id);
      if (result.restored_disabled) alert("O componente foi restaurado desativado porque seu estado antigo não é compatível com as relações atuais.");
    } catch (error) { overlay.querySelector(".dialog-error").textContent = error.message; button.disabled = false; }
    finally { overlay.dataset.busy = "false"; }
  });
}

function openComponentManagement(mod, component) {
  const overlay = openComponentDialog(
    "Gerenciar componente",
    `<p><b>${escapeHtml(component.name)}</b></p><div class="component-management-actions"><button class="btn component-update-files">Atualizar arquivos</button><button class="btn component-open-history" ${(component.versions || []).length ? "" : "disabled"}>Histórico (${(component.versions || []).length})</button><button class="btn danger-outline component-remove-safe">Remover componente</button></div><p>Atualizar preserva nome, rótulo, ordem e estado. A versão anterior fica disponível no histórico.</p>`,
  );
  overlay.querySelector(".component-update-files").onclick = () => { overlay.remove(); void importComponentsIntoMod(mod, { targetComponentId: component.id }); };
  overlay.querySelector(".component-open-history").onclick = () => { overlay.remove(); openComponentHistory(mod, component); };
  overlay.querySelector(".component-remove-safe").onclick = async (event) => {
    event.target.disabled = true;
    try {
      const preview = await api().preview_remove_component(mod.id, component.id);
      if (!preview?.ok) throw new Error(preview?.error || "Não foi possível revisar a remoção.");
      if (!preview.can_remove) throw new Error(preview.last_component ? "O último componente não pode ser removido; remova o mod inteiro." : `Remova primeiro as dependências: ${(preview.dependents || []).join(", ")}`);
      if (!confirm(`Remover “${preview.name}” do mod? Os arquivos continuarão na biblioteca e poderão ser restaurados.`)) { event.target.disabled = false; return; }
      overlay.dataset.busy = "true";
      const result = await api().remove_component(mod.id, component.id);
      if (!result?.ok) throw new Error(result?.error || "Não foi possível remover o componente.");
      overlay.remove(); await reloadAll(); await showModDetailsPage(mod.id);
    } catch (error) { overlay.querySelector(".dialog-error").textContent = error.message; event.target.disabled = false; }
    finally { overlay.dataset.busy = "false"; }
  };
}

function enhanceComponentManagement(mod) {
  const section = document.querySelector("#mod-detail-content .components-section");
  if (!section) return;
  const help = section.querySelector(".detail-component-help");
  if (help && !state.componentOrderEditing) help.textContent = "Selecione itens para editar o rótulo, ou arraste PAK/UCAS/UTOC/ZIP/RAR/7z aqui para adicionar variantes.";
  section.querySelectorAll(".detail-component").forEach((row) => {
    const component = (mod.components || []).find((item) => String(item.id) === String(row.dataset.componentId));
    if (!component) return;
    row.querySelector(".component-content")?.insertAdjacentHTML("beforeend", componentOriginSummary(component));
    const actions = row.querySelector(".component-actions");
    if (actions && !state.componentOrderEditing) {
      const button = document.createElement("button");
      button.className = "component-extra-action component-manage";
      button.title = "Atualizar, restaurar versão ou remover";
      button.textContent = "⋯";
      button.onclick = () => openComponentManagement(mod, component);
      actions.querySelector(".component-switch")?.before(button);
    }
  });
  if ((mod.removed_components || []).length) {
    const restore = document.createElement("button");
    restore.className = "detail-inline-add"; restore.id = "restore-removed-components";
    restore.textContent = `Restaurar (${mod.removed_components.length})`;
    restore.onclick = () => openRemovedComponents(mod);
    section.querySelector("h2")?.appendChild(restore);
  }
  if (state.componentOrderEditing) return;
  let dragDepth = 0;
  section.ondragenter = (event) => { if (!event.dataTransfer?.types?.includes("Files")) return; event.preventDefault(); dragDepth += 1; section.classList.add("is-file-dragover"); };
  section.ondragover = (event) => { if (!event.dataTransfer?.types?.includes("Files")) return; event.preventDefault(); event.dataTransfer.dropEffect = "copy"; };
  section.ondragleave = () => { dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) section.classList.remove("is-file-dragover"); };
  section.ondrop = (event) => {
    event.preventDefault(); dragDepth = 0; section.classList.remove("is-file-dragover");
    const paths = [...(event.dataTransfer?.files || [])]
      .map((file) => file.pywebviewFullPath || file.path || "")
      .filter(Boolean);
    if (!paths.length) { alert("O Windows não forneceu os caminhos dos arquivos arrastados. Use o botão + para selecioná-los."); return; }
    void importComponentsIntoMod(mod, { filepaths: paths });
  };
}

function renderModDetailsPage(mod, serial) {
  const gallery = mod.gallery_images || (mod.image_url ? [{ name: mod.image || "", url: mod.image_url }] : []);
  const heroBadge = mod.character && mod.character !== "Generic"
    ? `<span class="detail-character-badge">${mod.hero_icon_url ? `<img src="${mod.hero_icon_url}" alt="">` : ""}<span>${escapeHtml(mod.character)}</span></span>`
    : "";
  const typeBadges = (mod.types || [mod.type || "Unknown"]).map((type) => {
    const typeClass = `type-${String(type).toLowerCase().replace(/[^a-z]/g, "")}`;
    return `<span class="detail-type-badge ${typeClass}">${escapeHtml(type)}</span>`;
  }).join("");
  const packageInfo = mod.bundle_information || {};
  const informationBadges = [
    packageInfo.iostore ? `<span class="detail-info-badge iostore" title="Este mod usa o formato IoStore (.utoc/.ucas).">IO Store Bundle</span>` : "",
    packageInfo.hybrid ? `<span class="detail-info-badge hybrid" title="Contém dados IoStore e assets raw/legados.">Hybrid</span>` : "",
    packageInfo.encrypted ? `<span class="detail-info-badge encrypted" title="Este pacote foi instalado com a opção de criptografia.">Encrypted</span>` : "",
    packageInfo.raw_assets ? `<span class="detail-info-badge raw" title="Este mod não contém arquivos UAsset detectáveis no pacote.">Raw Assets</span>` : "",
  ].join("");
  const galleryHtml = gallery.length
    ? gallery.map((image, index) => `<div class="detail-gallery-item ${isGalleryVideo(image) ? "is-video" : ""}" data-index="${index}" title="${escapeHtml(galleryImageLabel(image))}">${galleryPreview(image)}<span class="gallery-image-title">${isGalleryVideo(image) ? "▶ " : ""}${escapeHtml(galleryImageLabel(image))}</span><button class="remove-gallery-image" data-image="${encodeURIComponent(image.name)}" title="Remover mídia">×</button></div>`).join("")
    : `<div class="detail-gallery-empty">▧<span>Este mod ainda não tem imagens.</span></div>`;
  const addons = mod.background_addons || [];
  const cinematics = [
    ...(mod.cinematics || []),
    ...addons.filter((addon) => addon.enabled).flatMap((addon) => (addon.cinematics || []).map((item) => ({
      ...item,
      enabled: item.enabled !== false,
      addonEnabled: Boolean(addon.enabled),
      addonName: addon.name,
    }))),
  ];
  const cinematicFileCounts = cinematics.reduce((counts, item) => {
    const key = cinematicConflictKey(item);
    if (key) counts.set(key, (counts.get(key) || 0) + 1);
    return counts;
  }, new Map());
  function cinematicConflictKey(item) {
    const filename = String(item.file || "").replace(/\\/g, "/").split("/").pop().toLowerCase();
    return `${String(item.category || "Outros").toLowerCase()}|${String(item.location || "Outros").toLowerCase()}|${filename}`;
  }
  const cinematicConflictColors = ["#ff4b58", "#51a9ff", "#ffc857", "#bd7cff", "#45d6bd", "#ff8dce", "#8bd450"];
  const cinematicByKey = new Map(cinematics.map((item) => [`${item.mod_id || mod.id}:${item.component_id}`, item]));
  const cinematicConflictGroups = new Map(
    [...cinematicFileCounts.entries()]
      .filter(([, count]) => count > 1)
      .map(([key]) => key)
      .sort()
      .map((key, index) => [key, { number: index + 1, color: cinematicConflictColors[index % cinematicConflictColors.length] }]),
  );
  const distinctAudioChoices = [...new Map(
    cinematics.flatMap((item) => item.audio_choices || [])
      .map((choice) => [`${choice.mod_id}:${choice.component_id}`, choice])
  ).values()];
  const audioPickerGroups = [...distinctAudioChoices.reduce((groups, choice) => {
    groups.set(choice.package, [...(groups.get(choice.package) || []), choice]);
    return groups;
  }, new Map()).entries()];
  const audioPickerHtml = `<div class="audio-picker-overlay" id="audio-picker" hidden><section class="audio-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="audio-picker-title"><header><div><b id="audio-picker-title">Escolher áudio</b><small id="audio-picker-target"></small></div><button id="close-audio-picker" title="Fechar">×</button></header><div class="audio-picker-player" id="audio-picker-player" hidden><b id="audio-picker-playing"></b><audio id="audio-picker-element" controls></audio></div><div class="audio-picker-groups">${audioPickerGroups.length ? audioPickerGroups.map(([packageName, choices], index) => `<details class="audio-picker-package" ${index === 0 ? "open" : ""}><summary><span>▸ ${escapeHtml(packageName)} <i>${choices.length}</i></span><span class="audio-picker-package-actions"><button class="audio-package-rename" data-audio-package-id="${choices[0].mod_id}" data-audio-package-name="${encodeURIComponent(packageName)}" title="Renomear pacote">✎</button><button class="audio-package-remove" data-audio-package-id="${choices[0].mod_id}" data-audio-package-name="${encodeURIComponent(packageName)}" title="Remover pacote">×</button></span></summary><div class="audio-picker-cards">${choices.map((choice) => `<article class="audio-picker-card"><button class="audio-picker-choice" data-audio-mod="${choice.mod_id}" data-audio-component="${choice.component_id}"><span class="audio-picker-icon">♫</span><span><b>${escapeHtml(choice.name)}</b><small>${choice.enabled ? "ativo" : "desativado"}</small></span></button><button class="audio-picker-listen" data-audio-mod="${choice.mod_id}" data-audio-component="${choice.component_id}" data-audio-name="${encodeURIComponent(choice.name)}" title="Ouvir neste painel">▶</button></article>`).join("")}</div></details>`).join("") : `<p class="detail-empty-text">Adicione primeiro um PAK de áudio.</p>`}</div></section></div>`;
  const cinematicCard = (item) => {
    const key = cinematicConflictKey(item);
    const overlapCount = cinematicFileCounts.get(key) || 0;
    const conflictGroup = cinematicConflictGroups.get(key);
    const conflictAlert = conflictGroup
      ? `<span class="cinematic-conflict-alert" style="--cinematic-conflict-color:${conflictGroup.color}" title="Grupo ${conflictGroup.number}: esta cinematic aparece em ${overlapCount} versões e uma substituirá a outra.">⚠</span>`
      : "";
    const audio = item.audio_binding;
    const audioControls = audio
      ? `<small class="cinematic-audio">🔊 Áudio: ${escapeHtml(audio.package)} · ${escapeHtml(audio.name)}${audio.pending_enabled !== null && audio.pending_enabled !== undefined ? " · aguardando o jogo fechar" : ""}</small><div class="cinematic-audio-actions"><button class="component-switch cinematic-audio-switch ${(audio.pending_enabled ?? audio.enabled) ? "on" : ""}" data-audio-mod="${audio.mod_id}" data-audio-component="${audio.component_id}" data-audio-enabled="${(audio.pending_enabled ?? audio.enabled) ? "1" : "0"}" title="Ativar/desativar áudio"><span></span></button><button class="cinematic-audio-unlink" data-cinematic-mod="${item.mod_id || mod.id}" data-cinematic-component="${item.component_id}" title="Desvincular áudio">×</button></div>`
      : `<button class="cinematic-audio-link" data-cinematic-mod="${item.mod_id || mod.id}" data-cinematic-component="${item.component_id}">Vincular áudio</button>`;
    const previewAvailable = mod.cinematic_preview_available !== false;
    const previewTitle = previewAvailable
      ? "Prévia BK2 (Bink Player opcional)"
      : "Prévia indisponível: o Bink Player não faz parte do Manager";
    return `<article class="cinematic-card ${item.addonEnabled === false || item.enabled === false ? "disabled" : ""}"><button class="cinematic-preview" data-cinematic-preview="${item.component_id}" data-cinematic-mod="${item.mod_id || mod.id}" title="${previewTitle}" ${previewAvailable ? "" : "disabled aria-disabled=\"true\""}>▶<small>${escapeHtml(item.short_category || item.category)}</small></button><div class="cinematic-copy"><div class="cinematic-title"><span class="cinematic-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>${conflictAlert}</div>${item.purpose ? `<small class="cinematic-purpose" title="${escapeHtml(item.purpose)}">${escapeHtml(item.purpose)}</small>` : ""}${item.addonName ? `<small class="cinematic-source">Complemento: ${escapeHtml(item.addonName)}</small>` : ""}${audioControls}<code title="${escapeHtml(item.file)}">${escapeHtml(item.file)}</code></div><button class="component-switch cinematic-switch ${item.enabled ? "on" : ""}" data-component-id="${item.component_id}" data-component-mod="${item.mod_id || mod.id}" title="Ativar/desativar esta cinematic"><span></span></button>${item.mod_id ? `<button class="cinematic-remove" data-component-id="${item.component_id}" data-component-mod="${item.mod_id}" data-cinematic-name="${encodeURIComponent(item.name)}" title="Remover esta cinematic do complemento">×</button>` : ""}</article>`;
  };
  const cinematicGallery = (items) => {
    const stacks = items.reduce((groups, item) => {
      const key = cinematicConflictKey(item);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
      return groups;
    }, new Map());
    return `<div class="cinematic-gallery">${[...stacks.values()].map((stack) => `<div class="cinematic-stack">${stack.map((item) => cinematicCard(item)).join("")}</div>`).join("")}</div>`;
  };
  const mapCinematicCategories = ["Entrada da partida", "Fim da partida", "Carregamento da partida"];
  const mapCinematicGroups = {};
  const otherCinematicGroups = {};
  cinematics.forEach((item) => {
    const category = item.category || "Outros";
    const location = item.location || "Outros";
    if (mapCinematicCategories.includes(category)) {
      mapCinematicGroups[location] ||= {};
      mapCinematicGroups[location][category] ||= [];
      mapCinematicGroups[location][category].push(item);
      return;
    }
    otherCinematicGroups[category] ||= {};
    otherCinematicGroups[category][location] ||= [];
    otherCinematicGroups[category][location].push(item);
  });
  const cinematicsCollapsed = state.collapsedCinematicSections.has(mod.id);
  const cinematicSectionStates = state.cinematicSectionStates.get(mod.id) || new Map();
  const cinematicOpen = (key) => cinematicSectionStates.get(encodeURIComponent(key)) !== false ? "open" : "";
  const cinematicCategoryOrder = ["Vídeos dos telões", "Login e Lobby", "Esportes", "Inicialização do jogo"];
  const cinematicCategorySort = ([a], [b]) => {
    const orderA = cinematicCategoryOrder.indexOf(a);
    const orderB = cinematicCategoryOrder.indexOf(b);
    return (orderA < 0 ? cinematicCategoryOrder.length : orderA) - (orderB < 0 ? cinematicCategoryOrder.length : orderB) || a.localeCompare(b, "pt-BR");
  };
  const renderMapGroups = () => Object.entries(mapCinematicGroups).sort(([a], [b]) => a.localeCompare(b, "pt-BR")).map(([location, categories]) => {
    const mapKey = `map:${location}`;
    const total = Object.values(categories).flat().length;
    return `<details class="cinematic-category cinematic-map" data-cinematic-section="${encodeURIComponent(mapKey)}" ${cinematicOpen(mapKey)}><summary>${escapeHtml(location)} <span>${total}</span></summary>${mapCinematicCategories.filter((category) => categories[category]?.length).map((category) => { const categoryKey = `map-category:${location}/${category}`; const items = categories[category]; return `<details class="cinematic-location" data-cinematic-section="${encodeURIComponent(categoryKey)}" ${cinematicOpen(categoryKey)}><summary>${escapeHtml(category)} <span>${items.length}</span></summary>${cinematicGallery(items)}</details>`; }).join("")}</details>`;
  }).join("");
  const renderOtherGroups = () => Object.entries(otherCinematicGroups).sort(cinematicCategorySort).map(([category, locations]) => {
    const categoryKey = `category:${category}`;
    return `<details class="cinematic-category" data-cinematic-section="${encodeURIComponent(categoryKey)}" ${cinematicOpen(categoryKey)}><summary>${escapeHtml(category)} <span>${Object.values(locations).flat().length}</span></summary>${Object.entries(locations).sort(([a], [b]) => a.localeCompare(b, "pt-BR")).map(([location, items]) => { const locationKey = `location:${category}/${location}`; return `<details class="cinematic-location" data-cinematic-section="${encodeURIComponent(locationKey)}" ${cinematicOpen(locationKey)}><summary>${escapeHtml(location)} <span>${items.length}</span></summary>${cinematicGallery(items)}</details>`; }).join("")}</details>`;
  }).join("");
  const cinematicsHtml = cinematics.length ? `<section class="detail-section cinematic-section ${cinematicsCollapsed ? "is-collapsed" : ""}"><h2>Cinematics <span>${cinematics.length}</span>${mod.install_target === "marvel_content" ? `<button class="detail-inline-add" id="add-background-audio">+ Áudio</button>` : ""}<button class="components-collapse-toggle" id="toggle-cinematics" title="${cinematicsCollapsed ? "Mostrar cinematics" : "Esconder cinematics"}" aria-label="${cinematicsCollapsed ? "Mostrar cinematics" : "Esconder cinematics"}">${cinematicsCollapsed ? "▸" : "▾"}</button></h2>${cinematicsCollapsed ? "" : `<div class="cinematic-groups">${renderMapGroups()}${renderOtherGroups()}</div>`}</section>` : "";
  const addonsHtml = mod.install_target === "marvel_content" ? `<section class="detail-section background-addons"><h2>Complementos <span>${addons.length}</span><button class="detail-inline-add" id="add-background-addon">+ Complemento</button></h2><p class="detail-component-help">As cinematics de um complemento aparecem apenas quando ele está ativo. Clique com o botão direito em um complemento para renomeá-lo.</p>${addons.length ? `<div class="detail-components">${addons.map((addon) => `<div class="detail-component background-addon-row ${addon.enabled ? "enabled" : "disabled"}" data-addon-id="${addon.id}" data-addon-name="${encodeURIComponent(addon.name)}" title="Botão direito para renomear"><div class="component-content"><b>${escapeHtml(addon.name)}</b><small>${addon.file_count} arquivo(s) · ${addon.enabled ? "ativo sobre este perfil" : "somente prévia"}</small></div><button class="component-switch background-addon-switch ${addon.enabled ? "on" : ""}" data-addon-id="${addon.id}" title="Ativar/desativar complemento"><span></span></button><button class="background-addon-remove" data-addon-id="${addon.id}" data-addon-name="${encodeURIComponent(addon.name)}" title="Remover complemento">×</button></div>`).join("")}</div>` : `<span class="detail-empty-text">Nenhum complemento adicionado.</span>`}</section>` : "";
  const components = mod.components || [];
  const activeComponent = components.find((component) => component.id === state.activeComponentContentId) || null;
  if (!activeComponent) {
    state.activeComponentContentId = null;
    state.componentContent = null;
  }
  const activeContent = activeComponent && state.componentContent?.component_id === activeComponent.id
    ? state.componentContent
    : null;
  const displayedAssetPaths = activeContent ? (activeContent.asset_paths || []) : (mod.asset_paths || []);
  const displayedFiles = activeContent ? (activeContent.files || []) : (mod.files || []);
  const displayedFileCount = displayedAssetPaths.length || displayedFiles.length;
  const detailContentLimit = 500;
  const rawDetailContents = displayedAssetPaths.length ? displayedAssetPaths : displayedFiles.map((file) => file.name);
  const detailContentsTruncated = !state.detailContentsExpanded && rawDetailContents.length > detailContentLimit;
  const visibleDetailContents = detailContentsTruncated ? rawDetailContents.slice(0, detailContentLimit) : rawDetailContents;
  const contents = displayedAssetPaths.length
    ? `<div class="asset-tree">${buildAssetTree(visibleDetailContents)}</div>`
    : `<ul class="details-files">${visibleDetailContents.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ul>`;
  const detailContentsMore = detailContentsTruncated
    ? `<button class="detail-inline-add detail-contents-more" id="show-all-detail-contents">Mostrar todos os ${rawDetailContents.length.toLocaleString("pt-BR")} arquivos</button>`
    : "";
  const availableComponentIds = new Set(components.map((component) => component.id));
  state.selectedComponentIds = new Set([...state.selectedComponentIds].filter((id) => availableComponentIds.has(id)));
  const selectedComponentIds = [...state.selectedComponentIds];
  const ordering = state.componentOrderEditing;
  const componentsCollapsed = state.collapsedComponentSections.has(mod.id);
  const componentBulkActions = selectedComponentIds.length && !ordering
    ? `<span class="component-bulk-actions"><b>${selectedComponentIds.length} selecionado(s)</b><button class="detail-inline-add" id="bulk-component-label">Rótulo</button><button class="detail-inline-add" id="move-components-up" title="Mover selecionados para cima">↑</button><button class="detail-inline-add" id="move-components-down" title="Mover selecionados para baixo">↓</button><button class="detail-inline-add" id="clear-component-selection" title="Limpar seleção">×</button></span>`
    : "";
  const hasMeshPreviewComponent = components.length > 0;
  const canAddComponents = !mod.install_target && !mod.background_audio;
  const componentsHtml = (components.length > 1 || hasMeshPreviewComponent) ? `<section class="detail-section components-section ${componentsCollapsed ? "is-collapsed" : ""}"><h2><button class="detail-inline-add component-order-toggle" id="edit-component-order">${ordering ? "Concluir ordem" : "Editar ordem"}</button> Componentes <span>${components.length}</span>${canAddComponents ? `<button class="detail-inline-add" id="add-mod-components" title="Adicionar variantes ou componentes a este mod">+</button>` : ""}<button class="components-collapse-toggle" id="toggle-components" title="${componentsCollapsed ? "Mostrar componentes" : "Esconder componentes"}" aria-label="${componentsCollapsed ? "Mostrar componentes" : "Esconder componentes"}">${componentsCollapsed ? "▸" : "▾"}</button>${componentBulkActions}</h2>${componentsCollapsed ? "" : `<p class="detail-component-help">${ordering ? "Arraste um componente ou o conjunto selecionado para mudar a ordem." : "Selecione itens para editar o rótulo ou mover vários juntos."}</p><div class="detail-components ${ordering ? "is-ordering" : ""}">${components.map((component, index) => { const labelData = `data-component-id="${component.id}" data-component-description="${encodeURIComponent(component.description || "")}"`; const selected = state.selectedComponentIds.has(component.id); const viewing = state.activeComponentContentId === component.id; const shortName = String(component.name || "").split(/[\\/]/).pop(); const displayName = components.filter(c => String(c.name || "").split(/[\\/]/).pop() === shortName).length > 1 ? component.name : shortName; const componentTypes = Array.isArray(component.types) && component.types.length ? component.types : (component.type ? [component.type] : []); const inferredTypes = componentTypes.length ? componentTypes : (/physics/i.test(displayName) ? ["Physics"] : /texture|textura|^t_/i.test(displayName) ? ["Texture"] : /mesh|^s[mk]_/i.test(displayName) ? ["Mesh"] : []); const isMesh = inferredTypes.includes("Mesh"); const label = component.description || (isMesh ? "Principal" : "Acompanhamento"); const typeBadges = inferredTypes.map((type) => `<small class="component-type-badge component-type-${String(type).toLowerCase()}">${escapeHtml(type)}</small>`).join(""); return `<div class="detail-component ${component.enabled ? "enabled" : "disabled"} ${selected ? "is-selected" : ""} ${viewing ? "is-viewing-content" : ""}" data-component-id="${component.id}" ${ordering ? "draggable=\"true\"" : ""}><label class="component-select-wrap" title="Selecionar componente"><input class="component-select" type="checkbox" data-component-id="${component.id}" ${selected ? "checked" : ""}></label><div class="component-content"><b>${escapeHtml(displayName)}</b><button class="component-description" ${labelData} title="Editar rótulo">${component.files.length} arquivo(s) · ${escapeHtml(label)}</button></div><div class="component-actions">${typeBadges}${ordering ? `<span class="component-drag-handle" title="Arraste um componente ou o grupo selecionado">⠿</span>` : `<button class="component-content-view" data-component-id="${component.id}" title="Mostrar somente os arquivos deste componente">${viewing ? "Todos" : "Conteúdo"}</button><button class="component-label-edit" ${labelData} title="Editar rótulo">Rótulo</button><button class="component-rename" data-component-id="${component.id}" data-component-name="${encodeURIComponent(component.name)}" title="Editar nome">Nome</button><button class="component-switch ${component.enabled ? "on" : ""}" data-component-id="${component.id}" title="Ativar/desativar componente"><span></span></button>`}</div></div>`; }).join("")}</div>`}</section>` : "";
  const tags = mod.tags.length
    ? mod.tags.map(tag => `<button class="detail-tag detail-tag-remove" data-tag="${encodeURIComponent(tag)}" title="Remover tag">${escapeHtml(tag)} <span>×</span></button>`).join("")
    : `<span class="detail-empty-text">Nenhuma tag adicionada.</span>`;
  const link = mod.link
    ? `<a class="details-link" href="${escapeHtml(mod.link)}" target="_blank" rel="noopener">${escapeHtml(mod.link)}</a>`
    : `<span class="detail-empty-text">Nenhum link salvo.</span>`;
  document.getElementById("mod-detail-content").innerHTML = `
    <div class="detail-title-row"><h1>${escapeHtml(mod.name)}</h1><button class="detail-path-action detail-identity-edit" id="edit-mod-identity" title="Corrigir personagem e skin sem o scan desfazer a escolha">Corrigir</button></div>
    <section class="detail-type-section"><div class="detail-caption">TIPO E PERSONAGEM</div><div class="detail-badges">${heroBadge}${typeBadges}${mod.skin ? `<span class="detail-skin-badge">${escapeHtml(mod.skin)}</span>` : ""}</div></section>
    <section class="detail-section"><h2>Galeria <span>${gallery.length}</span><button class="detail-inline-add" id="add-gallery-images" title="Adicionar imagens ou vídeos à galeria">+ Mídia</button></h2><div class="detail-gallery">${galleryHtml}</div></section>
    ${cinematicsHtml}
    ${audioPickerHtml}
    ${addonsHtml}
    <section class="detail-section"><h2>Tags <button class="detail-inline-add" id="add-detail-tag" title="Adicionar tag">+</button></h2><div class="detail-tags">${tags}</div></section>
    ${componentsHtml}
    <section class="detail-section detail-information"><h2>Detalhes</h2>
      <div class="detail-caption">INFORMAÇÕES</div><div class="detail-info-badges">${informationBadges || `<span class="detail-empty-text">Sem metadados adicionais.</span>`}</div>
      <div class="detail-facts"><div><small>Assets</small><b>${mod.asset_count || mod.file_count || 0}</b></div><div><small>Tamanho</small><b>${(mod.size_mb || 0).toFixed(2)} MB</b></div><div><small>Pasta</small><b>${escapeHtml(mod.folder || "—")}</b></div></div>
      <div class="details-label">CAMINHO DO MOD</div>
      <div class="detail-path-row"><code title="${escapeHtml(mod.install_path || "")}">${escapeHtml(mod.install_path || "—")}</code><button class="detail-path-action" id="copy-mod-path">Copiar</button><button class="detail-path-action" id="open-mod-path">Abrir pasta</button></div>
      <div class="details-label">LINK DO MOD</div><div class="detail-link-row"><div class="details-value detail-link-value">${link}</div><button class="detail-path-action" id="edit-mod-link">Editar</button>${mod.link ? `<button class="detail-path-action" id="open-mod-link">Abrir link</button>` : ""}</div>
      <div class="details-label">ARQUIVOS${activeComponent ? ` — ${escapeHtml(activeComponent.name)}` : ""} (${displayedFileCount} ARQUIVOS)${activeComponent ? ` <button class="detail-inline-add" id="show-all-file-contents">Todos os conteúdos</button>` : ""}</div>${detailContentsMore}${contents}
    </section>`;
  enhanceComponentManagement(mod);
  const cinematicPreviews = document.querySelectorAll("#mod-detail-content .cinematic-preview");
  if (cinematicPreviews.length) {
    state.cinematicPreviewIndex = Math.min(state.cinematicPreviewIndex, cinematicPreviews.length - 1);
    activateCinematicPreview(state.cinematicPreviewIndex, false, false);
  }
  document.querySelectorAll(".component-switch:not(.cinematic-switch):not(.background-addon-switch)").forEach((button) => button.onclick = async () => {
    button.disabled = true;
    try {
      const result = await api().toggle_component(mod.id, button.dataset.componentId);
      if (!result?.ok) throw new Error(result?.error || "Não foi possível alterar o componente.");
      await refreshModInState(mod.id);
      renderLocalChange();
      const content = document.getElementById("mod-detail-content"), scrollTop = content.scrollTop;
      await showModDetailsPage(mod.id, { onlyIfOpen: true });
      if (state.detailsModId === mod.id) content.scrollTop = scrollTop;
    } catch (error) { alert(error.message); }
    finally { button.disabled = false; }
  });
  if (!ordering) {
    document.querySelectorAll(".detail-component[data-component-id]").forEach((row) => {
      const component = components.find((item) => item.id === row.dataset.componentId);
      const types = component?.types || (component?.type ? [component.type] : []);
      if (!types.includes("Mesh")) return;
      const viewerAction = document.createElement("button");
      viewerAction.className = "component-3d-open";
      viewerAction.textContent = "3D";
      viewerAction.title = "Visualizar este Mesh dentro do CrabVault";
      viewerAction.onclick = () => {
        if (!window.Marvel3DViewer?.open) {
          alert("O visualizador 3D ainda não terminou de carregar.");
          return;
        }
        window.Marvel3DViewer.open({
          modId: mod.id,
          componentId: component.id,
          componentName: component.name,
        });
      };
      const actions = row.querySelector(".component-actions");
      actions?.prepend(viewerAction);
    });
  }
  if (!mod.install_target && !ordering) {
    document.querySelectorAll("#mod-detail-content .detail-component").forEach(row => {
      const component = components.find(c => c.id === row.dataset.componentId);
      if (!component) return;
      const actions = row.querySelector(".component-actions");
      const diagnosis = document.createElement("button");
      diagnosis.className = "component-extra-action";
      diagnosis.textContent = "Diagnóstico";
      diagnosis.onclick = () => showComponentDiagnosis(mod, component).catch(error => alert(error.message));
      actions?.appendChild(diagnosis);
      const rules = document.createElement("button");
      rules.className = "component-extra-action";
      rules.textContent = "Relações";
      rules.onclick = () => showComponentRules(mod, component);
      actions?.appendChild(rules);
      const statusNames = {missing:"Arquivos ausentes", pending:"Análise pendente", read_error:"Falha de leitura", unrecognized:"Tipo não reconhecido"};
      if (statusNames[component.classification_status]) {
        const status = document.createElement("small");
        status.textContent = statusNames[component.classification_status];
        row.querySelector(".component-content")?.appendChild(status);
      }
      if (component.exclusive_group || component.requires?.length) {
        const note = document.createElement("small");
        note.textContent = [component.exclusive_group ? `Alternativa: ${component.exclusive_group}` : "",
          component.requires?.length ? `${component.requires.length} dependência(s)` : ""].filter(Boolean).join(" · ");
        row.querySelector(".component-content")?.appendChild(note);
      }
    });
  }
  if (typeof simplifyComponentActions === "function") simplifyComponentActions(mod, components, ordering);
  document.querySelectorAll("[data-cinematic-preview]").forEach((button) => button.onclick = async () => {
    const result = await api().open_cinematic_preview(button.dataset.cinematicMod || mod.id, button.dataset.cinematicPreview);
    if (!result?.ok) alert(result?.error || "Não foi possível abrir a prévia.");
  });
  document.querySelectorAll("details[data-cinematic-section]").forEach((section) => section.addEventListener("toggle", () => {
    const sectionStates = state.cinematicSectionStates.get(mod.id) || new Map();
    sectionStates.set(section.dataset.cinematicSection, section.open);
    state.cinematicSectionStates.set(mod.id, sectionStates);
  }));
  document.querySelectorAll(".cinematic-switch").forEach((button) => button.onclick = async () => {
    button.disabled = true;
    try {
      const result = await api().toggle_component(button.dataset.componentMod || mod.id, button.dataset.componentId);
      if (!result?.ok) return alert(result?.error || "Não foi possível alterar a cinematic.");
      if (result.disabled_conflicts?.length) alert("A versão selecionada foi ativada e as outras versões desse mesmo vídeo foram desativadas.");
      await showModDetailsPage(mod.id);
    } catch (error) {
      alert(`Não foi possível alterar a cinematic: ${error?.message || error}`);
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  });
  document.querySelectorAll(".cinematic-remove").forEach((button) => button.onclick = async () => {
    const name = decodeURIComponent(button.dataset.cinematicName);
    if (!confirm(`Remover a cinematic "${name}" deste complemento? Os outros vídeos do complemento serão mantidos.`)) return;
    button.disabled = true;
    const result = await api().remove_background_cinematic(button.dataset.componentMod, button.dataset.componentId);
    if (!result?.ok) return alert(result?.error || "Não foi possível remover a cinematic.");
    await showModDetailsPage(mod.id);
  });
  document.getElementById("add-background-addon")?.addEventListener("click", () => beginInstall("background", mod.id));
  document.getElementById("add-background-audio")?.addEventListener("click", () => beginInstall("background_audio", mod.id));
  document.querySelectorAll(".cinematic-audio-link").forEach((button) => button.onclick = async () => {
    const key = `${button.dataset.cinematicMod}:${button.dataset.cinematicComponent}`;
    const cinematic = cinematicByKey.get(key);
    const choices = cinematic?.audio_choices || [];
    if (!choices.length) return alert("Adicione primeiro um PAK de áudio pelo botão + Áudio em Cinematics.");
    const picker = document.getElementById("audio-picker");
    picker.hidden = false;
    document.getElementById("audio-picker-target").textContent = `Escolha o banco para “${cinematic.name}”.`;
    picker.dataset.cinematicMod = button.dataset.cinematicMod;
    picker.dataset.cinematicComponent = button.dataset.cinematicComponent;
  });
  const audioPicker = document.getElementById("audio-picker");
  const closeAudioPicker = () => { if (audioPicker) audioPicker.hidden = true; };
  document.getElementById("close-audio-picker")?.addEventListener("click", closeAudioPicker);
  audioPicker?.addEventListener("click", (event) => { if (event.target === audioPicker) closeAudioPicker(); });
  document.querySelectorAll(".audio-picker-choice").forEach((button) => button.onclick = async () => {
    button.disabled = true;
    const result = await api().bind_background_audio(audioPicker.dataset.cinematicMod, audioPicker.dataset.cinematicComponent, button.dataset.audioMod, button.dataset.audioComponent);
    if (!result?.ok) { button.disabled = false; return alert(result?.error || "Não foi possível vincular o áudio."); }
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".audio-package-rename").forEach((button) => button.onclick = async (event) => {
    event.preventDefault(); event.stopPropagation();
    const oldName = decodeURIComponent(button.dataset.audioPackageName);
    const name = prompt("Novo nome do pacote de áudio:", oldName);
    if (name === null || !name.trim() || name.trim() === oldName) return;
    const result = await api().rename_mod(button.dataset.audioPackageId, name.trim());
    if (!result?.ok) return alert(result?.error || "Não foi possível renomear o pacote.");
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".audio-package-remove").forEach((button) => button.onclick = async (event) => {
    event.preventDefault(); event.stopPropagation();
    const name = decodeURIComponent(button.dataset.audioPackageName);
    if (!confirm(`Remover o pacote de áudio "${name}" da biblioteca? Os vínculos deixarão de aparecer nas cinematics.`)) return;
    const result = await api().delete_mod(button.dataset.audioPackageId);
    if (!result?.ok) return alert(result?.error || "Não foi possível remover o pacote.");
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".cinematic-audio-switch").forEach((button) => button.onclick = async () => {
    button.disabled = true;
    const result = await api().set_background_audio_enabled(button.dataset.audioMod, button.dataset.audioComponent, button.dataset.audioEnabled !== "1");
    if (!result?.ok) alert(result?.error || "Não foi possível alterar o áudio.");
    else if (result.queued) alert("Alteração de áudio agendada. Ela será aplicada automaticamente quando o Marvel Rivals fechar.");
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".cinematic-audio-unlink").forEach((button) => button.onclick = async () => {
    if (!confirm("Desvincular este áudio da cinematic? O banco continuará salvo na biblioteca.")) return;
    button.disabled = true;
    const result = await api().unbind_background_audio(button.dataset.cinematicMod, button.dataset.cinematicComponent);
    if (!result?.ok) return alert(result?.error || "Não foi possível desvincular o áudio.");
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".audio-picker-listen").forEach((button) => button.onclick = async () => {
    button.disabled = true;
    const result = await api().get_background_audio_preview(button.dataset.audioMod, button.dataset.audioComponent);
    button.disabled = false;
    if (!result?.ok) return alert(result?.error || "Não foi possível preparar a prévia de áudio.");
    const playerBox = document.getElementById("audio-picker-player");
    const player = document.getElementById("audio-picker-element");
    document.getElementById("audio-picker-playing").textContent = `Tocando: ${decodeURIComponent(button.dataset.audioName)}`;
    playerBox.hidden = false;
    player.src = result.data_url;
    player.play().catch(() => {});
  });
  document.querySelectorAll(".background-addon-switch").forEach((button) => button.onclick = async () => {
    button.disabled = true;
    try {
      const result = await api().toggle_mod(button.dataset.addonId);
      if (!result?.ok) return alert(result?.error || "Não foi possível alterar o complemento.");
      if (result.disabled_conflicts?.length) alert("O complemento foi ativado; versões concorrentes dos mesmos vídeos foram desativadas.");
      await showModDetailsPage(mod.id);
    } catch (error) {
      alert(`Não foi possível alterar o complemento: ${error?.message || error}`);
    } finally {
      if (button.isConnected) button.disabled = false;
    }
  });
  document.querySelectorAll(".background-addon-remove").forEach((button) => button.onclick = async (event) => {
    event.stopPropagation();
    const name = decodeURIComponent(button.dataset.addonName);
    if (!confirm(`Remover o complemento "${name}"? Ele será apagado da biblioteca, sem alterar o Background principal.`)) return;
    button.disabled = true;
    const result = await api().delete_mod(button.dataset.addonId || button.dataset.audioAddonId);
    if (!result?.ok) return alert(result?.error || "Não foi possível remover o complemento.");
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".background-addon-row").forEach((row) => row.oncontextmenu = async (event) => {
    event.preventDefault();
    const oldName = decodeURIComponent(row.dataset.addonName);
    const newName = prompt("Novo nome do complemento:", oldName);
    if (newName === null || !newName.trim() || newName.trim() === oldName) return;
    const result = await api().rename_mod(row.dataset.addonId, newName.trim());
    if (!result?.ok) return alert(result?.error || "Não foi possível renomear o complemento.");
    await showModDetailsPage(mod.id);
  });
  document.querySelectorAll(".component-rename").forEach((button) => button.onclick = async () => {
    const oldName = decodeURIComponent(button.dataset.componentName);
    const name = prompt("Nome do componente:", oldName);
    if (name === null || !name.trim() || name.trim() === oldName) return;
    const result = await api().rename_component(mod.id, button.dataset.componentId, name.trim());
    if (result.ok) await showModDetailsPage(mod.id);
    else alert(result.error || "Não foi possível renomear o componente.");
  });
  document.querySelectorAll(".component-description, .component-label-edit").forEach((button) => button.onclick = async (event) => {
    event.stopPropagation();
    const current = decodeURIComponent(button.dataset.componentDescription);
    await openComponentLabelMenu(button, mod, button.dataset.componentId, current);
  });
  document.querySelectorAll(".component-content-view").forEach((button) => button.onclick = async (event) => {
    event.stopPropagation();
    const componentId = button.dataset.componentId;
    if (state.activeComponentContentId === componentId) {
      state.activeComponentContentId = null;
      state.componentContent = null;
      await showModDetailsPage(mod.id);
      return;
    }
    button.disabled = true;
    const result = await api().get_component_file_contents(mod.id, componentId);
    button.disabled = false;
    if (!result?.ok) return alert(result?.error || "Não foi possível abrir o conteúdo do componente.");
    state.activeComponentContentId = componentId;
    state.componentContent = result;
    await showModDetailsPage(mod.id);
  });
  document.getElementById("show-all-detail-contents")?.addEventListener("click", async () => {
    state.detailContentsExpanded = true;
    await showModDetailsPage(mod.id);
  });
  const showAllFileContents = document.getElementById("show-all-file-contents");
  if (showAllFileContents) showAllFileContents.onclick = async () => {
    state.activeComponentContentId = null;
    state.componentContent = null;
    await showModDetailsPage(mod.id);
  };
  document.querySelectorAll(".component-select").forEach((input) => input.onclick = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const componentId = input.dataset.componentId;
    const componentIds = components.map((component) => component.id);
    const anchorIndex = componentIds.indexOf(state.lastSelectedComponentId);
    const currentIndex = componentIds.indexOf(componentId);
    if (event.shiftKey && anchorIndex >= 0 && currentIndex >= 0) {
      const range = componentIds.slice(
        Math.min(anchorIndex, currentIndex),
        Math.max(anchorIndex, currentIndex) + 1,
      );
      if (event.ctrlKey) range.forEach((id) => state.selectedComponentIds.delete(id));
      else range.forEach((id) => state.selectedComponentIds.add(id));
    } else if (state.selectedComponentIds.has(componentId)) {
      state.selectedComponentIds.delete(componentId);
    } else {
      state.selectedComponentIds.add(componentId);
    }
    state.lastSelectedComponentId = componentId;
    await showModDetailsPage(mod.id);
  });
  const bulkLabelButton = document.getElementById("bulk-component-label");
  if (bulkLabelButton) bulkLabelButton.onclick = async () => {
    await openComponentLabelMenu(bulkLabelButton, mod, [...state.selectedComponentIds], "");
  };
  ["up", "down"].forEach((direction) => {
    const button = document.getElementById(`move-components-${direction}`);
    if (button) button.onclick = async () => {
      button.disabled = true;
      const result = await api().move_components(mod.id, [...state.selectedComponentIds], direction);
      if (!result?.ok) alert(result?.error || "Não foi possível mover os componentes.");
      await showModDetailsPage(mod.id);
    };
  });
  const clearComponentSelection = document.getElementById("clear-component-selection");
  if (clearComponentSelection) clearComponentSelection.onclick = async () => {
    state.selectedComponentIds.clear();
    state.lastSelectedComponentId = null;
    await showModDetailsPage(mod.id);
  };
  const editOrderButton = document.getElementById("edit-component-order");
  if (editOrderButton) editOrderButton.onclick = async () => {
    state.componentOrderEditing = !state.componentOrderEditing;
    await showModDetailsPage(mod.id);
  };
  const addModComponentsButton = document.getElementById("add-mod-components");
  if (addModComponentsButton) addModComponentsButton.onclick = () => void importComponentsIntoMod(mod, { button: addModComponentsButton });
  const toggleComponentsButton = document.getElementById("toggle-components");
  if (toggleComponentsButton) toggleComponentsButton.onclick = async () => {
    if (state.collapsedComponentSections.has(mod.id)) state.collapsedComponentSections.delete(mod.id);
    else state.collapsedComponentSections.add(mod.id);
    await showModDetailsPage(mod.id);
  };
  const toggleCinematicsButton = document.getElementById("toggle-cinematics");
  if (toggleCinematicsButton) toggleCinematicsButton.onclick = async () => {
    if (state.collapsedCinematicSections.has(mod.id)) state.collapsedCinematicSections.delete(mod.id);
    else state.collapsedCinematicSections.add(mod.id);
    await showModDetailsPage(mod.id);
  };
  if (ordering) {
    const componentList = document.querySelector(".detail-components.is-ordering");
    let dragged = null;
    let draggedItems = [];
    componentList?.querySelectorAll(".detail-component").forEach((item) => {
      item.ondragstart = (event) => {
        dragged = item;
        const selected = new Set([...state.selectedComponentIds].map(String));
        draggedItems = selected.has(String(item.dataset.componentId))
          ? [...componentList.querySelectorAll(".detail-component")].filter((entry) => selected.has(String(entry.dataset.componentId)))
          : [item];
        draggedItems.forEach((entry) => entry.classList.add("dragging"));
        event.dataTransfer.effectAllowed = "move";
      };
      item.ondragend = () => {
        draggedItems.forEach((entry) => entry.classList.remove("dragging"));
        dragged = null;
        draggedItems = [];
        componentList.querySelectorAll(".drag-over").forEach((entry) => entry.classList.remove("drag-over"));
      };
      item.ondragover = (event) => {
        event.preventDefault();
        if (!dragged || dragged === item) return;
        componentList.querySelectorAll(".drag-over").forEach((entry) => entry.classList.remove("drag-over"));
        item.classList.add("drag-over");
        const before = event.clientY < item.getBoundingClientRect().top + item.offsetHeight / 2;
        if (draggedItems.includes(item)) return;
        const anchor = before ? item : item.nextSibling;
        draggedItems.forEach((entry) => componentList.insertBefore(entry, anchor));
      };
    });
    componentList?.addEventListener("drop", async (event) => {
      event.preventDefault();
      const componentIds = [...componentList.querySelectorAll(".detail-component")].map((item) => item.dataset.componentId);
      const result = await api().reorder_components(mod.id, componentIds);
      if (result.ok) await showModDetailsPage(mod.id);
      else alert(result.error || "Não foi possível salvar a ordem.");
    });
  }
  document.getElementById("add-gallery-images").onclick = async () => {
    const result = await api().add_detail_images(mod.id);
    if (result && result.ok) await showModDetailsPage(mod.id);
    else if (result && !result.cancelled) alert(result.error || "Não foi possível adicionar as imagens.");
  };
  document.querySelectorAll(".remove-gallery-image").forEach((button) => button.onclick = async () => {
    if (!confirm("Remover esta mídia da galeria?")) return;
    const result = await api().remove_detail_image(mod.id, decodeURIComponent(button.dataset.image));
    if (result && result.ok) await showModDetailsPage(mod.id);
    else alert((result && result.error) || "Não foi possível remover a imagem.");
  });
  document.querySelectorAll(".detail-gallery-item").forEach((item) => {
    const image = gallery[Number(item.dataset.index)];
    const preview = item.querySelector("img, video, .gallery-media-placeholder");
    if (preview) preview.onclick = () => openGalleryViewer(mod, Number(item.dataset.index));
    item.oncontextmenu = (event) => showGalleryImageMenu(event, mod, image);
  });
  document.getElementById("add-detail-tag").onclick = async () => {
    openAssignTagMenu(document.getElementById("add-detail-tag"), mod, async () => {
      await showModDetailsPage(mod.id);
      renderLocalChange();
    });
  };
  document.querySelectorAll(".detail-tag-remove").forEach((button) => button.onclick = async () => {
    const tag = decodeURIComponent(button.dataset.tag);
    await api().remove_tag(mod.id, tag);
    state.tags = await api().get_tags();
    renderTags();
    await showModDetailsPage(mod.id);
  });
  document.getElementById("edit-mod-identity").onclick = () => openIdentityCorrectionDialog(mod);
  const copyPath = document.getElementById("copy-mod-path");
  copyPath.onclick = async () => {
    const path = mod.install_path || "";
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
    } catch (_) {
      const input = document.createElement("textarea");
      input.value = path;
      document.body.appendChild(input);
      input.select();
      document.execCommand("copy");
      input.remove();
    }
    copyPath.textContent = "Copied";
    setTimeout(() => { copyPath.textContent = "Copy"; }, 1400);
  };
  document.getElementById("open-mod-path").onclick = async () => {
    const result = await api().open_mod_folder(mod.id);
    if (!result.ok) alert("Não foi possível abrir a pasta do mod.");
  };
  document.getElementById("edit-mod-link").onclick = async () => {
    const link = prompt("Link do mod (deixe vazio para remover):", mod.link || "");
    if (link === null) return;
    const result = await api().set_mod_link(mod.id, link.trim());
    if (result && result.ok) await showModDetailsPage(mod.id);
    else alert((result && result.error) || "Não foi possível salvar o link.");
  };
  const openLink = document.getElementById("open-mod-link");
  if (openLink) openLink.onclick = () => window.open(mod.link, "_blank", "noopener");
  document.getElementById("details-panel").classList.remove("open");
  const overlay = document.getElementById("mod-detail-overlay");
  overlay.classList.add("open");
  overlay.setAttribute("aria-hidden", "false");
  renderMods();
  loadDetailGalleryPreviews(mod, serial);
  if (mod.component_classification_pending) {
    const section = document.querySelector("#mod-detail-content .components-section");
    section?.insertAdjacentHTML("beforeend", '<p class="detail-component-help" id="component-classification-status" role="status">Analisando componentes…</p>');
    completeComponentClassification(mod);
  }
}

function closeModDetailsPage() {
  detailRequestSerial += 1;
  pendingDetailRequest = null;
  detailPreviewQueue.length = 0;
  state.detailsModId = null;
  state.detailContentsExpanded = false;
  state.componentOrderEditing = false;
  state.selectedComponentIds.clear();
  state.lastSelectedComponentId = null;
  const overlay = document.getElementById("mod-detail-overlay");
  overlay.classList.remove("open");
  overlay.setAttribute("aria-hidden", "true");
  document.getElementById("mod-detail-content").setAttribute("aria-busy", "false");
  renderMods();
  drainThumbnailQueue();
}
document.getElementById("mod-detail-close").onclick = closeModDetailsPage;
document.getElementById("mod-detail-close-icon").onclick = closeModDetailsPage;

async function showDetails(modId) {
  const mod = await api().get_mod_details(modId, false);
  if (!mod) return;
  preserveModThumbnail(mod, state.mods.find(item => item.id === modId));
  state.detailsModId = modId;
  document.getElementById("details-panel").classList.add("open");
  const image = mod.image_url ? `<img class="details-cover" src="${mod.image_url}" alt="Capa">` : "";
  const link = mod.link ? `<a class="details-link" href="${escapeHtml(mod.link)}" target="_blank">Abrir link do mod</a>` : "—";
  const area = document.getElementById("details-content");
  area.className = "details-body";
  area.innerHTML = `${image}<h2 class="details-title">${escapeHtml(mod.name)}</h2><div class="details-label">TIPO E PERSONAGEM</div><div class="details-value">${escapeHtml(mod.character)} · ${escapeHtml(mod.type)}${mod.skin ? " · " + escapeHtml(mod.skin) : ""}</div><div class="details-label">INFORMAÇÕES</div><div class="details-value">${mod.enabled ? "Ativado" : "Desativado"} · ${mod.size_mb.toFixed(2)} MB</div><div class="details-label">LINK DO MOD</div><div class="details-value">${link}</div><div class="details-label">ARQUIVOS (${mod.file_count})</div><ul class="details-files">${mod.files.map(f => `<li>${escapeHtml(f.name)}</li>`).join("")}</ul>`;
  renderMods();
}

document.getElementById("details-close").onclick = () => {
  state.detailsModId = null;
  document.getElementById("details-panel").classList.remove("open");
  renderMods();
};

// ---------------------------------------------------------
// Modal: Add Mod (com seletor Character -> Skin)
// ---------------------------------------------------------
const addModOverlay = document.getElementById("add-mod-overlay");
const characterListBox = document.getElementById("character-list-box");
const characterSearch = document.getElementById("character-search");
const characterPicker = document.getElementById("character-picker");
const characterSelected = document.getElementById("character-selected");
const skinSection = document.getElementById("skin-section");
const skinChipsWrap = document.getElementById("skin-chips");
const inputSkinNew = document.getElementById("input-skin-new");

function updateSuggestedInstallFolder() {
  if (state.installFolderChosenManually || !state.pickedCharacter) return;
  const source = (state.installSourceFolder || "Mod").trim() || "Mod";
  const skin = (state.pickedSkin || "Default").trim() || "Default";
  document.getElementById("input-folder").value = state.pickedCharacter === "Generic"
    ? source
    : `${state.pickedCharacter}\\${skin}\\${source}`;
}

function renderCharacterPicker(filter) {
  const q = (filter || "").toLowerCase();
  characterListBox.innerHTML = "";
  state.roster
    .filter((name) => name.toLowerCase().includes(q))
    .forEach((name) => {
      const row = document.createElement("div");
      row.className = "picker-row";
      row.textContent = name;
      row.onclick = () => selectCharacter(name);
      characterListBox.appendChild(row);
    });
}

characterSearch.addEventListener("input", () => renderCharacterPicker(characterSearch.value));

async function selectCharacter(name, { preserveCorrection = false } = {}) {
  if (!preserveCorrection) clearPersonalImportChoice("Identidade editada. As correções salvas foram desmarcadas.");
  state.pickedCharacter = name;
  state.pickedSkin = "";
  characterPicker.style.display = "none";
  characterSelected.style.display = "inline-flex";
  document.getElementById("install-character-badge").textContent = name;
  characterSelected.innerHTML = `${escapeHtml(name)} <span class="change-btn" id="change-character">Alterar</span>`;
  document.getElementById("change-character").onclick = () => {
    clearPersonalImportChoice("Identidade editada. As correções salvas foram desmarcadas.");
    characterPicker.style.display = "block";
    characterSelected.style.display = "none";
    state.pickedCharacter = null;
  };

  skinSection.style.display = "block";
  inputSkinNew.value = "";
  updateSuggestedInstallFolder();
  const skins = await api().get_skins_for_character(name);
  skinChipsWrap.innerHTML = "";
  skins.forEach((skin) => {
    const chip = document.createElement("div");
    chip.className = "skin-chip";
    chip.textContent = skin;
    chip.onclick = () => {
      clearPersonalImportChoice("Identidade editada. As correções salvas foram desmarcadas.");
      state.pickedSkin = skin;
      inputSkinNew.value = skin;
      updateSuggestedInstallFolder();
      skinChipsWrap.querySelectorAll(".skin-chip").forEach((c) => c.classList.remove("selected"));
      chip.classList.add("selected");
    };
    skinChipsWrap.appendChild(chip);
  });
}

inputSkinNew.addEventListener("input", () => {
  clearPersonalImportChoice("Identidade editada. As correções salvas foram desmarcadas.");
  state.pickedSkin = inputSkinNew.value.trim();
  updateSuggestedInstallFolder();
  skinChipsWrap.querySelectorAll(".skin-chip").forEach((c) => {
    c.classList.toggle("selected", c.textContent === state.pickedSkin);
  });
});
document.getElementById("input-folder").addEventListener("input", () => { state.installFolderChosenManually = true; });

function addInstallTag(value) {
  const tag = (value || "").trim();
  const wrap = document.getElementById("install-tags");
  if (!tag || [...wrap.children].some(chip => chip.dataset.tag === tag)) return;
  const chip = document.createElement("span");
  chip.className = "skin-chip";
  chip.dataset.tag = tag;
  chip.textContent = `${tag} ×`;
  chip.onclick = () => chip.remove();
  wrap.appendChild(chip);
}

function renderInstallTree() {
  const wrap = document.getElementById("install-tree-list");
  if (!wrap) return;
  const expanded = new Set();
  function nodeMarkup(node, depth) {
    const children = node.children || [];
    const hasChildren = children.length > 0;
    const id = encodeURIComponent(node.path);
    return `<div class="install-tree-node" data-path="${escapeHtml(node.path)}" data-depth="${depth}">
      <button class="install-tree-toggle" data-node="${id}" ${hasChildren ? "" : "disabled"}>${hasChildren ? "▸" : ""}</button><span>📁 ${escapeHtml(node.name)}</span></div>
      <div class="install-tree-children" data-parent="${id}" hidden>${children.map(child => nodeMarkup(child, depth + 1)).join("")}</div>`;
  }
  wrap.innerHTML = state.folders.map(root => (root.children || []).map(child => nodeMarkup(child, 0)).join("")).join("");
  wrap.querySelectorAll(".install-tree-toggle:not([disabled])").forEach(button => button.onclick = (event) => {
    event.stopPropagation();
    const branch = wrap.querySelector(`[data-parent="${button.dataset.node}"]`);
    branch.hidden = !branch.hidden;
    button.textContent = branch.hidden ? "▸" : "▾";
  });
  wrap.querySelectorAll(".install-tree-node").forEach(node => node.onclick = () => {
    state.installFolderChosenManually = true;
    document.getElementById("input-folder").value = node.dataset.path;
  });
}
window.openInstallTagMenu = () => {
  const menu = document.getElementById("install-tag-menu");
  const button = document.getElementById("install-tag-plus");
  const rect = button.getBoundingClientRect();
  menu.style.position = "fixed";
  menu.style.left = `${rect.left}px`;
  menu.style.top = `${rect.bottom + 5}px`;
  menu.innerHTML = "";
  const fresh = document.createElement("button");
  fresh.textContent = "+ Nova tag…";
  fresh.onclick = () => { menu.classList.remove("open"); openCreateTagDialog(async (tag) => addInstallTag(tag)); };
  menu.appendChild(fresh);
  state.tags.forEach((tag) => {
    const option = document.createElement("button");
    option.className = "catalog-option";
    option.innerHTML = `<span>${escapeHtml(tag.name)}</span><span class="catalog-remove" title="Excluir tag">×</span>`;
    option.onclick = () => { addInstallTag(tag.name); menu.classList.remove("open"); };
    option.querySelector(".catalog-remove").onclick = async (event) => {
      event.stopPropagation();
      if (!confirm(`Excluir a tag \"${tag.name}\" de todos os mods?`)) return;
      const result = await api().delete_tag_catalog(tag.name);
      if (!result || !result.ok) return alert(result?.error || "Não foi possível excluir a tag.");
      state.tags = result.tags || [];
      state.installTags = state.installTags.filter((item) => item.casefold() !== tag.name.casefold());
      renderInstallTags();
      window.openInstallTagMenu();
    };
    menu.appendChild(option);
  });
  menu.classList.toggle("open");
};
document.getElementById("install-tag-plus").onclick = window.openInstallTagMenu;
document.getElementById("btn-install-image").onclick = async () => {
  if (!state.installToken) return;
  const result = await api().choose_install_image(state.installToken);
  if (result && result.ok) {
    const preview = document.getElementById("install-image-preview");
    preview.src = result.image_url;
    preview.style.display = "block";
    document.getElementById("input-wants-image").checked = true;
  }
};
document.getElementById("install-image-plus").onclick = () => document.getElementById("btn-install-image").click();

async function beginInstall(kind, parentBackgroundId = null) {
  if (state.importBusy || state.installToken) return;
  if (pendingOperation()) { await resumeLastOperation(); return; }
  try {
    const requestId = newOperationRequest("prepare");
    const descriptor = { requestId, title: "Preparando importação", context: { kind: "import_prepare", install_kind: kind, parent_background_id: parentBackgroundId } };
    const picked = await runImportOperation(() => api().start_mod_import(requestId, kind, parentBackgroundId), descriptor.title, descriptor);
    await openInstallSelection(picked, parentBackgroundId, descriptor);
  } catch (error) { alert(error.message); }
}

async function openInstallSelection(picked, parentBackgroundId = null, descriptor = null) {
  if (!picked || picked.cancelled) return;
  if (!picked.ok) { alert(picked.error || "Não foi possível ler os arquivos."); return; }
  if (descriptor) rememberPreparedImport(descriptor);
  const specialInstall = ["reshade", "background", "background_audio"].includes(picked.install_kind);
  state.installKind = picked.install_kind || "pak";
  state.installParentBackgroundId = parentBackgroundId;
  state.installToken = picked.token;
  state.installSourceFolder = picked.source_folder || "";
  state.installFolderChosenManually = false;
  renderPersonalImportChoices(specialInstall ? null : picked.personal_corrections);
  document.querySelector("#add-mod-overlay .modal-body").scrollTop = 0;
  const coverButton = document.getElementById("btn-install-image");
  coverButton.style.display = "inline-flex";
  coverButton.style.visibility = "visible";
  document.getElementById("input-name").value = "";
  document.getElementById("input-link").value = "";
  document.getElementById("input-wants-image").checked = false;
  document.getElementById("input-folder").value = picked.suggested_folder || "";
  document.getElementById("install-tags").innerHTML = "";
  document.getElementById("install-image-preview").removeAttribute("src");
  document.getElementById("install-image-preview").style.display = "none";
  characterSearch.value = "";
  state.pickedCharacter = specialInstall ? "Generic" : null;
  state.pickedSkin = "";
  characterPicker.style.display = specialInstall ? "none" : "block";
  characterSelected.style.display = "none";
  skinSection.style.display = "none";
  document.getElementById("install-character-label").style.display = specialInstall ? "none" : "block";
  document.getElementById("install-modal-title").textContent = state.installKind === "reshade" ? "Instalar ReShade" : state.installKind === "background" ? "Instalar cinemáticas" : state.installKind === "background_audio" ? "Adicionar áudio ao Background" : "Instalar mods";
  document.getElementById("install-modal-hint").textContent = state.installKind === "reshade"
    ? "O conteúdo do ZIP/RAR/7z será guardado na biblioteca e instalado, preservando pastas, em Marvel\\Binaries\\Win64."
    : state.installKind === "background"
      ? "O conteúdo do ZIP/RAR/7z será guardado na biblioteca e mesclado, preservando pastas, em Marvel\\Content\\Marvel. O MoviesBink original será salvo antes da primeira alteração."
      : state.installKind === "background_audio"
        ? "O PAK será guardado na biblioteca e separado em bancos de áudio individuais. Eles só serão instalados quando você ativar os switches correspondentes."
    : "Os tipos são detectados pelos arquivos selecionados. As variações ficam guardadas na biblioteca e podem ser alternadas nos detalhes do mod.";

  if (state.roster.length === 0) {
    state.roster = await api().get_character_roster();
  }
  renderCharacterPicker("");
  document.getElementById("input-name").value = "";
  document.getElementById("install-original-name").textContent = picked.suggested_name || "";
  document.getElementById("install-character-badge").textContent = picked.character || "Generic";
  document.getElementById("install-type-badge").textContent = picked.type || "Unknown";
  if (!specialInstall) await selectCharacter(picked.character || "Generic");
  if (picked.skin) {
    state.pickedSkin = picked.skin;
    inputSkinNew.value = picked.skin;
    updateSuggestedInstallFolder();
  }
  addModOverlay.classList.add("open");
  requestAnimationFrame(() => { document.querySelector("#add-mod-overlay .modal-body").scrollTop = 0; });
}
document.getElementById("btn-add-mod").onclick = () => beginInstall("pak");
document.getElementById("btn-add-reshade").onclick = () => beginInstall("reshade");
document.getElementById("btn-add-background").onclick = () => beginInstall("background");

async function cancelPendingInstall() {
  if (state.importBusy || state.installCancelling) return;
  state.installCancelling = true;
  try {
    if (state.installToken) {
      const result = await api().cancel_mod_install(state.installToken);
      if (!result?.ok) throw new Error(result?.error || "Não foi possível descartar a preparação.");
    }
    state.installToken = null;
    state.installParentBackgroundId = null;
    clearPreparedImport();
    addModOverlay.classList.remove("open");
  } catch (error) {
    alert("Não foi possível cancelar a seleção. Tente novamente.\n\n" + error.message);
  } finally {
    state.installCancelling = false;
  }
}
document.getElementById("add-mod-close").onclick = cancelPendingInstall;
document.getElementById("add-mod-cancel").onclick = cancelPendingInstall;

document.getElementById("add-mod-confirm").onclick = async () => {
  if (state.importBusy || state.installCancelling || !state.installToken) return;
  if (state.installKind !== "reshade" && !state.pickedCharacter) {
    alert("Escolha um personagem antes de continuar.");
    return;
  }
  const meta = {
    name: document.getElementById("input-name").value.trim(),
    character: state.pickedCharacter,
    skin: state.pickedSkin,
    link: document.getElementById("input-link").value.trim(),
    folder: document.getElementById("input-folder").value.trim(),
    source_folder: state.installSourceFolder,
    personal_correction_choice: state.personalCorrectionChoice || null,
    tags: [...document.querySelectorAll("#install-tags .skin-chip")].map((tag) => tag.dataset.tag),
    install_options: {},
  };

  const confirmBtn = document.getElementById("add-mod-confirm");
  const originalLabel = confirmBtn.textContent;
  confirmBtn.disabled = true;
  confirmBtn.textContent = "Instalando…";
  const token = state.installToken, parentBackgroundId = state.installParentBackgroundId;
  const importStartedAt = globalThis.performance?.now?.() ?? Date.now();
  let submitted = false, installed = false;
  const closeSelection = () => {
    state.installToken = null;
    state.installParentBackgroundId = null;
    clearPreparedImport();
    addModOverlay.classList.remove("open");
  };

  try {
    const res = await runImportOperation(() => {
      submitted = true;
      return api().start_complete_mod_install(token, meta);
    }, "Instalando mod", { requestId: `install:${token}`, context: { kind: "import_commit", parent_background_id: parentBackgroundId } });
    if (submitted) closeSelection();
    if (res && res.ok) {
      installed = true;
      const reloadStartedAt = globalThis.performance?.now?.() ?? Date.now();
      await reloadAll();
      const reloadFinishedAt = globalThis.performance?.now?.() ?? Date.now();
      if (res.source_cleanup?.errors?.length) alert("O mod foi instalado, mas alguns arquivos de origem foram preservados:\n" + res.source_cleanup.errors.map(item => item.error || item.path).join("\n"));
      if (parentBackgroundId) await showModDetailsPage(parentBackgroundId);
      const importFinishedAt = globalThis.performance?.now?.() ?? Date.now();
      if (typeof recordImportTiming === "function") void recordImportTiming({
        kind: state.installKind || "pak",
        mod_id: res.record?.id || parentBackgroundId || "",
        commit_ms: reloadStartedAt - importStartedAt,
        reload_ms: reloadFinishedAt - reloadStartedAt,
        detail_ms: importFinishedAt - reloadFinishedAt,
        total_ms: importFinishedAt - importStartedAt,
        backend_ms: res.backend_ms || 0,
      });
    } else if (res && res.cancelled) {
      return;
    } else if (res && res.error) {
      alert("Não foi possível instalar o mod:\n\n" + res.error + "\n\nSe a operação foi interrompida, consulte Operações interrompidas nas configurações.");
    } else {
      alert("Não foi possível confirmar o resultado da instalação. Atualize a biblioteca e consulte Operações interrompidas nas configurações antes de importar novamente.");
    }
  } catch (err) {
    if (submitted) closeSelection();
    alert(installed
      ? "O mod foi instalado, mas não foi possível atualizar a interface. Atualize a biblioteca.\n\n" + err.message
      : "Não foi possível confirmar o resultado da instalação. Atualize a biblioteca e consulte Operações interrompidas nas configurações antes de importar novamente.\n\n" + err.message);
  } finally {
    confirmBtn.disabled = false;
    confirmBtn.textContent = originalLabel;
  }
};

// ---------------------------------------------------------
// Modal: Settings
// ---------------------------------------------------------
const settingsOverlay = document.getElementById("settings-overlay");
let pendingAccentColor = DEFAULT_ACCENT;
let pendingThemeMode = DEFAULT_THEME;

function renderAccentPicker(color) {
  const accent = isHexColor(color) ? color : DEFAULT_ACCENT;
  document.querySelectorAll(".accent-choice").forEach((button) => {
    const selected = button.dataset.accent.toLowerCase() === accent.toLowerCase();
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function renderThemePicker(theme) {
  const selectedTheme = theme === "light" ? "light" : DEFAULT_THEME;
  document.querySelectorAll(".theme-choice").forEach((button) => {
    const selected = button.dataset.theme === selectedTheme;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}

function closeSettings({ restoreAppearance = true } = {}) {
  if (restoreAppearance) {
    applyAccentColor(state.settings.accent_color);
    applyThemeMode(state.settings.theme_mode);
  }
  settingsOverlay.classList.remove("open");
}

document.getElementById("btn-settings").onclick = async () => {
  document.getElementById("settings-mods-path").value = state.settings.mods_path || "";
  void refreshNative3dSupportStatus();
  document.getElementById("auto-detect-status").textContent = "";
  document.getElementById("setting-hide-suffix").checked = !!state.settings.hide_file_suffix;
  document.getElementById("setting-auto-details").checked = state.settings.auto_open_details !== false;
  document.getElementById("setting-show-type-badge").checked = !!state.settings.show_type_badge;
  document.getElementById("setting-bypass-game-lock").checked = !!state.settings.bypass_game_running_lock;
  document.getElementById("setting-preserve-import-archives").checked = state.settings.preserve_import_archives !== false;
  document.getElementById("setting-delete-import-sources").checked = state.settings.delete_import_sources_after_success !== false;
  document.getElementById("setting-language").value = normalizedLanguage(state.settings.ui_language);
  document.getElementById("library-health-result").innerHTML = "";
  void refreshCharacterCatalogStatus();
  pendingAccentColor = isHexColor(state.settings.accent_color) ? state.settings.accent_color : DEFAULT_ACCENT;
  pendingThemeMode = state.settings.theme_mode === "light" ? "light" : DEFAULT_THEME;
  applyAccentColor(pendingAccentColor);
  applyThemeMode(pendingThemeMode);
  renderAccentPicker(pendingAccentColor);
  renderThemePicker(pendingThemeMode);
  settingsOverlay.classList.add("open");
};
document.getElementById("setting-export-backup").onclick = async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await api().export_library_backup_dialog();
    if (!result?.cancelled && !result?.ok) {
      alert(result?.error || "Não foi possível criar o backup.");
    } else if (result?.ok) {
      alert(`Backup criado com ${result.mods || 0} mod(s).\n${result.path}`);
    }
  } catch (error) {
    alert(`Não foi possível criar o backup: ${error}`);
  } finally {
    button.disabled = false;
  }
};
document.getElementById("setting-restore-backup").onclick = async (event) => {
  if (!confirm("Restaurar um backup substitui o catálogo e as configurações atuais. Os arquivos no mods_storage e na pasta do jogo não serão apagados. Continuar?")) return;
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await api().restore_library_backup_dialog();
    if (!result?.cancelled && !result?.ok) {
      alert(result?.error || "Não foi possível restaurar o backup.");
      return;
    }
    if (result?.ok) {
      state.settings = await api().get_settings();
      applyAccentColor(state.settings.accent_color);
      applyThemeMode(state.settings.theme_mode);
      await reloadAll();
      closeSettings({ restoreAppearance: false });
      alert(`Backup restaurado: ${result.mods || 0} mod(s) no catálogo.`);
    }
  } catch (error) {
    alert(`Não foi possível restaurar o backup: ${error}`);
  } finally {
    button.disabled = false;
  }
};
document.querySelectorAll(".accent-choice").forEach((button) => {
  button.onclick = () => {
    pendingAccentColor = button.dataset.accent;
    applyAccentColor(pendingAccentColor);
    renderAccentPicker(pendingAccentColor);
  };
});
document.querySelectorAll(".theme-choice").forEach((button) => {
  button.onclick = () => {
    pendingThemeMode = button.dataset.theme === "light" ? "light" : DEFAULT_THEME;
    applyThemeMode(pendingThemeMode);
    renderThemePicker(pendingThemeMode);
  };
});
document.getElementById("settings-close").onclick = () => closeSettings();
document.getElementById("setting-review-tutorial").onclick = () => {
  const language = document.getElementById("setting-language").value;
  closeSettings();
  openTutorial(language);
};
function characterCatalogStatusText(result) {
  const english = normalizedLanguage(document.getElementById("setting-language")?.value || state.settings.ui_language) === "en";
  const total = Number(result?.total || 0).toLocaleString(english ? "en-US" : "pt-BR");
  if (result?.error && result?.ok === false) {
    return english
      ? `The last check failed; the local catalog remains active (${total} entries). ${result.error}`
      : `A última verificação falhou; o catálogo local continua ativo (${total} entradas). ${result.error}`;
  }
  if (!result?.checked_at) {
    return english ? `Local catalog active (${total} entries). No online check recorded yet.`
      : `Catálogo local ativo (${total} entradas). Ainda não há verificação online registrada.`;
  }
  const date = new Date(result.checked_at);
  const when = Number.isNaN(date.getTime()) ? result.checked_at : date.toLocaleString(english ? "en-US" : "pt-BR");
  return english ? `Catalog active with ${total} entries. Last check: ${when}.`
    : `Catálogo ativo com ${total} entradas. Última verificação: ${when}.`;
}
async function refreshCharacterCatalogStatus() {
  const target = document.getElementById("settings-character-catalog-status");
  if (!target) return;
  const english = normalizedLanguage(document.getElementById("setting-language")?.value || state.settings.ui_language) === "en";
  target.textContent = english ? "Checking local catalog…" : "Consultando catálogo local…";
  try {
    target.textContent = characterCatalogStatusText(await api().get_character_catalog_status());
  } catch (error) {
    target.textContent = english ? `Could not read the catalog status: ${error.message || error}`
      : `Não foi possível consultar o catálogo: ${error.message || error}`;
  }
}
async function applyCharacterCatalogResult(result) {
  if (result?.ok && result?.changed) {
    state.roster = await api().get_character_roster();
    await reloadAll();
  }
  const target = document.getElementById("settings-character-catalog-status");
  if (target) target.textContent = characterCatalogStatusText(result || {});
}
window.onCharacterCatalogUpdated = result => { void applyCharacterCatalogResult(result); };
document.getElementById("setting-update-character-catalog").onclick = async (event) => {
  const button = event.currentTarget;
  const english = normalizedLanguage(document.getElementById("setting-language")?.value || state.settings.ui_language) === "en";
  button.disabled = true;
  button.textContent = english ? "Updating…" : "Atualizando…";
  try {
    const result = await api().update_character_catalog();
    await applyCharacterCatalogResult(result);
  } catch (error) {
    document.getElementById("settings-character-catalog-status").textContent = english
      ? `Update failed; the local catalog was preserved. ${error.message || error}`
      : `A atualização falhou; o catálogo local foi preservado. ${error.message || error}`;
  } finally {
    button.disabled = false;
    button.textContent = "Atualizar catálogo agora";
    window.setUiLanguage?.(state.settings.ui_language);
  }
};
function openAppUpdateDialog(result, english) {
  document.getElementById("app-update-overlay")?.remove();
  const previousFocus = document.activeElement;
  const text = (portuguese, englishText) => english ? englishText : portuguese;
  const overlay = document.createElement("div");
  overlay.id = "app-update-overlay";
  overlay.className = "modal-overlay open app-update-overlay";
  overlay.innerHTML = `<section class="app-update-dialog" role="alertdialog" aria-modal="true" aria-labelledby="app-update-title" aria-describedby="app-update-description" tabindex="-1">
    <header>
      <span class="app-update-brand" aria-hidden="true">🦀</span>
      <div><b id="app-update-title">${text("Atualização disponível", "Update available")}</b><small>CrabVault ${escapeHtml(result.latest_version)}</small></div>
      <button class="icon-btn app-update-close" aria-label="${text("Fechar", "Close")}">✕</button>
    </header>
    <div class="app-update-body" id="app-update-description">
      <h3>${text("Deseja instalar a nova versão agora?", "Install the new version now?")}</h3>
      <p class="app-update-summary">${text("O CrabVault baixará o instalador oficial e confirmará sua integridade antes de executá-lo.", "CrabVault will download the official installer and verify its integrity before running it.")}</p>
      <div class="app-update-facts">
        <p><span aria-hidden="true">✓</span><span><b>SHA-256</b><small>${text("O arquivo será verificado antes da instalação.", "The file will be verified before installation.")}</small></span></p>
        <p><span aria-hidden="true">✓</span><span><b>${text("Seus dados serão preservados", "Your data will be preserved")}</b><small>${text("Configurações, mods e mídias permanecerão no lugar.", "Settings, mods, and media will remain in place.")}</small></span></p>
        <p><span aria-hidden="true">↻</span><span><b>${text("O CrabVault será reiniciado", "CrabVault will restart")}</b><small>${text("O aplicativo será fechado para concluir a atualização.", "The application will close to complete the update.")}</small></span></p>
      </div>
    </div>
    <footer><button class="btn app-update-cancel">${text("Agora não", "Not now")}</button><button class="btn primary app-update-confirm">${text("Baixar e atualizar", "Download and update")}</button></footer>
  </section>`;
  const cancel = overlay.querySelector(".app-update-cancel");
  const confirmButton = overlay.querySelector(".app-update-confirm");
  const closeButton = overlay.querySelector(".app-update-close");
  document.body.appendChild(overlay);
  return new Promise(resolve => {
    const close = confirmed => {
      overlay.remove();
      previousFocus?.focus?.();
      resolve(confirmed);
    };
    closeButton.onclick = () => close(false);
    cancel.onclick = () => close(false);
    confirmButton.onclick = () => close(true);
    overlay.onclick = event => { if (event.target === overlay) close(false); };
    overlay.onkeydown = event => {
      if (event.key === "Escape") { event.preventDefault(); close(false); return; }
      if (event.key !== "Tab") return;
      const controls = [closeButton, cancel, confirmButton];
      const first = controls[0], last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      else if (!overlay.contains(document.activeElement)) { event.preventDefault(); cancel.focus(); }
    };
    confirmButton.focus();
  });
}

document.getElementById("setting-check-app-update").onclick = async (event) => {
  const button = event.currentTarget;
  const target = document.getElementById("settings-app-update-status");
  const english = normalizedLanguage(document.getElementById("setting-language")?.value || state.settings.ui_language) === "en";
  button.disabled = true;
  button.textContent = english ? "Checking…" : "Verificando…";
  target.textContent = english ? "Checking the latest stable GitHub release…" : "Consultando a release estável mais recente no GitHub…";
  try {
    const result = await api().check_app_update();
    if (!result?.ok) {
      target.textContent = result?.error || (english ? "Could not check for updates." : "Não foi possível verificar atualizações.");
    } else if (!result.available) {
      target.textContent = english ? `CrabVault ${result.current_version} is up to date.` : `O CrabVault ${result.current_version} está atualizado.`;
    } else {
      const size = result.download_size ? ` (${formatModSize(result.download_size / 1048576)})` : "";
      target.textContent = english ? `Version ${result.latest_version}${size} is available.` : `A versão ${result.latest_version}${size} está disponível.`;
      if (await openAppUpdateDialog(result, english)) {
        button.textContent = english ? "Downloading and verifying…" : "Baixando e verificando…";
        target.textContent = english ? "Downloading and verifying the installer. Keep CrabVault open…" : "Baixando e verificando o instalador. Mantenha o CrabVault aberto…";
        const installed = await api().install_app_update();
        if (!installed?.ok) target.textContent = installed?.error || (english ? "Update failed." : "A atualização falhou.");
        else target.textContent = english ? "Verified installer ready. CrabVault will close to update." : "Instalador verificado. O CrabVault será fechado para atualizar.";
      }
    }
  } catch (error) {
    target.textContent = english ? `Could not check for updates: ${error.message || error}` : `Não foi possível verificar atualizações: ${error.message || error}`;
  } finally {
    button.disabled = false;
    button.textContent = "Verificar atualizações";
    window.setUiLanguage?.(state.settings.ui_language);
  }
};
async function refreshNative3dSupportStatus() {
  const target = document.getElementById("settings-native3d-status");
  const english = normalizedLanguage(state.settings.ui_language) === "en";
  target.textContent = english ? "Checking local support…" : "Consultando suporte local…";
  try {
    const result = await api().get_native3d_support_status();
    target.textContent = !result.extractor_ready
      ? (english ? "The 3D extractor is missing. Extract the complete CrabVault package again." : "O extrator 3D está ausente. Extraia novamente o pacote completo do CrabVault.")
      : result.ready
        ? (english ? `Support installed. ${result.mapping || "Reader files are available for offline use."}` : `Suporte instalado. ${result.mapping || "Arquivos de leitura disponíveis para uso offline."}`)
        : (english ? "Support will be prepared when the 3D viewer is first opened. CrabVault will download the mapping, zlib, and Oodle 2.9.10 from WorkingRobot/OodleUE and verify their integrity." : "O suporte será preparado na primeira abertura 3D. O CrabVault baixará mapping, zlib e Oodle 2.9.10 do WorkingRobot/OodleUE, com verificação de integridade.");
  } catch (error) { target.textContent = english ? `Could not check support: ${error.message || error}` : `Não foi possível consultar o suporte: ${error.message || error}`; }
}
document.getElementById("btn-prepare-native3d").onclick = async (event) => {
  const button = event.currentTarget;
  const english = normalizedLanguage(state.settings.ui_language) === "en";
  button.disabled = true;
  try {
    const requestId = newOperationRequest("native3d_support");
    const result = await runImportOperation(() => api().start_native3d_support_update(requestId),
      "Preparando suporte 3D", { requestId, context: { kind: "native3d_support" } });
    await refreshNative3dSupportStatus();
    if (!result?.ok && !result?.cancelled) {
      document.getElementById("settings-native3d-status").textContent = result?.error || (english ? "Could not prepare 3D support." : "Não foi possível preparar o suporte 3D.");
    }
  } catch (error) {
    document.getElementById("settings-native3d-status").textContent = english ? `Preparation failed: ${error.message || error}` : `Falha na preparação: ${error.message || error}`;
  } finally { button.disabled = false; }
};
document.getElementById("settings-done").onclick = async () => {
  state.settings = await api().save_settings({
    hide_file_suffix: document.getElementById("setting-hide-suffix").checked,
    auto_open_details: document.getElementById("setting-auto-details").checked,
    show_type_badge: document.getElementById("setting-show-type-badge").checked,
    bypass_game_running_lock: document.getElementById("setting-bypass-game-lock").checked,
    preserve_import_archives: document.getElementById("setting-preserve-import-archives").checked,
    delete_import_sources_after_success: document.getElementById("setting-delete-import-sources").checked,
    ui_language: normalizedLanguage(document.getElementById("setting-language").value),
    theme_mode: pendingThemeMode,
    accent_color: pendingAccentColor,
  });
  applyAccentColor(state.settings.accent_color);
  applyThemeMode(state.settings.theme_mode);
  window.setUiLanguage?.(state.settings.ui_language);
  closeSettings({ restoreAppearance: false });
  renderMods();
};

// ---------------------------------------------------------
// Perfis de modlist
// ---------------------------------------------------------
async function openProfiles() {
  document.getElementById("profiles-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "profiles-overlay";
  overlay.className = "modal-overlay open";
  overlay.innerHTML = `<section class="profiles-dialog" role="dialog" aria-modal="true"><header><div><b>Perfis</b><small>Salve e recupere mods ativos e componentes.</small></div><button class="icon-btn" aria-label="Fechar">✕</button></header><div class="profiles-body"><div class="profiles-actions"><button class="btn primary" id="profile-save-current">＋ Salvar estado atual</button><button class="btn" id="profile-restore-last" disabled>↶ Reverter última alteração</button></div><div class="profiles-list">Carregando perfis…</div></div><footer><button class="btn" id="profiles-close">Fechar</button></footer></section>`;
  const close = () => overlay.remove();
  overlay.querySelector("header button").onclick = close;
  overlay.querySelector("#profiles-close").onclick = close;
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  document.body.appendChild(overlay);

  const renderProfiles = async () => {
    const [profiles, recovery] = await Promise.all([api().get_profiles(), api().get_recovery_snapshot()]);
    const recoveryButton = overlay.querySelector("#profile-restore-last");
    recoveryButton.disabled = !recovery?.available;
    recoveryButton.title = recovery?.available ? `Reverter: ${recovery.action || "última alteração"}` : "Nenhuma alteração em massa disponível";
    recoveryButton.textContent = recovery?.available ? "↶ Reverter última alteração" : "↶ Nada para reverter";
    const list = overlay.querySelector(".profiles-list");
    list.innerHTML = profiles.length ? profiles.map((profile) => `<article class="profile-row"><div><b>${escapeHtml(profile.name)}</b><small>${profile.mod_count} mod(s) no snapshot</small></div><div><button class="btn profile-apply" data-id="${profile.id}">Aplicar</button><button class="btn profile-update" data-id="${profile.id}" title="Substituir pelo estado atual">Atualizar</button><button class="btn danger-outline profile-delete" data-id="${profile.id}" title="Excluir perfil">✕</button></div></article>`).join("") : `<p class="profiles-empty">Nenhum perfil salvo ainda.</p>`;
    list.querySelectorAll(".profile-apply").forEach((button) => button.onclick = async () => {
      const profile = profiles.find((item) => item.id === button.dataset.id);
      if (!profile || !confirm(`Aplicar o perfil “${profile.name}”? Os switches e componentes atuais serão substituídos.`)) return;
      button.disabled = true;
      button.textContent = "Aplicando…";
      const result = await api().apply_profile(button.dataset.id);
      if (!result?.ok) alert(result?.error || "Não foi possível aplicar o perfil.");
      else {
        await reloadAll();
        alert(`Perfil “${profile.name}” aplicado em ${result.changed?.length || 0} mod(s).`);
      }
      await renderProfiles();
    });
    list.querySelectorAll(".profile-update").forEach((button) => button.onclick = async () => {
      const profile = profiles.find((item) => item.id === button.dataset.id);
      if (!profile || !confirm(`Atualizar o perfil “${profile.name}” com os mods e componentes atuais?`)) return;
      button.disabled = true;
      button.textContent = "Atualizando…";
      const result = await api().update_profile(button.dataset.id);
      if (!result?.ok) alert(result?.error || "Não foi possível atualizar o perfil.");
      await renderProfiles();
    });
    list.querySelectorAll(".profile-delete").forEach((button) => button.onclick = async () => {
      const profile = profiles.find((item) => item.id === button.dataset.id);
      if (!profile || !confirm(`Excluir o perfil “${profile.name}”?`)) return;
      const result = await api().delete_profile(button.dataset.id);
      if (!result?.ok) alert(result?.error || "Não foi possível excluir o perfil.");
      await renderProfiles();
    });
    recoveryButton.onclick = async () => {
      if (!recovery?.available || !confirm(`Reverter “${recovery.action || "a última alteração em massa"}”?\n\nIsso restaura switches e componentes; arquivos não serão apagados.`)) return;
      recoveryButton.disabled = true;
      recoveryButton.textContent = "Revertendo…";
      const result = await api().restore_last_recovery_snapshot();
      if (!result?.ok) alert(result?.error || "Não foi possível reverter a alteração.");
      else {
        await reloadAll();
        alert(`Alteração revertida em ${result.changed?.length || 0} mod(s).`);
      }
      await renderProfiles();
    };
  };
  overlay.querySelector("#profile-save-current").onclick = async () => {
    const name = prompt("Nome do novo perfil:");
    if (!name) return;
    const result = await api().save_profile(name);
    if (!result?.ok) alert(result?.error || "Não foi possível salvar o perfil.");
    await renderProfiles();
  };
  await renderProfiles();
}
document.getElementById("btn-profiles").onclick = openProfiles;

// ---------------------------------------------------------
// Histórico de alterações
// ---------------------------------------------------------
async function openHistory() {
  document.getElementById("history-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "history-overlay";
  overlay.className = "modal-overlay open";
  overlay.innerHTML = `<section class="history-dialog" role="dialog" aria-modal="true"><header><div><b>Histórico de atividade</b><small>Importações, exclusões, prioridades, perfis, conflitos e reparos.</small></div><button class="icon-btn" aria-label="Fechar">✕</button></header><div class="history-body"><div class="import-performance-list"></div><div class="history-filters"><input class="modal-input" id="history-search" placeholder="Buscar no histórico…"><select class="modal-input" id="history-action"><option value="">Todas as ações</option></select></div><div class="history-list">Carregando histórico…</div></div><footer><button class="btn danger-outline" id="history-clear-old">Limpar anteriores a 30 dias</button><button class="btn danger-outline" id="history-clear">Limpar tudo</button><button class="btn" id="history-close">Fechar</button></footer></section>`;
  const close = () => overlay.remove();
  overlay.querySelector("header button").onclick = close;
  overlay.querySelector("#history-close").onclick = close;
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  document.body.appendChild(overlay);

  const renderHistory = async () => {
    const [entries, performanceEntries] = await Promise.all([api().get_activity_log(), api().get_import_performance(5)]);
    const english = window.getUiLanguage?.() === "en";
    const text = (portuguese, englishText) => english ? englishText : portuguese;
    const localize = value => window.uiText?.(value) || value;
    const list = overlay.querySelector(".history-list");
    const timingList = overlay.querySelector(".import-performance-list");
    timingList.innerHTML = performanceEntries?.length ? `<details><summary>${text("Tempos das últimas importações", "Latest import timings")}</summary>${performanceEntries.map((entry) => `<p><b>${escapeHtml(entry.kind || text("importação", "import"))}</b> · total ${Math.round(entry.total_ms || 0)} ms · backend ${Math.round(entry.backend_ms || 0)} ms · ${text("atualização da biblioteca", "library update")} ${Math.round(entry.reload_ms || 0)} ms · ${text("detalhes", "details")} ${Math.round(entry.detail_ms || 0)} ms</p>`).join("")}</details>` : "";
    const actionSelect = overlay.querySelector("#history-action");
    const selectedAction = actionSelect.value;
    const actions = [...new Set(entries.map((entry) => String(entry.action || "alteração")))].sort();
    actionSelect.innerHTML = `<option value="">Todas as ações</option>${actions.map((action) => `<option value="${escapeHtml(action)}">${escapeHtml(action.replaceAll("_", " "))}</option>`).join("")}`;
    actionSelect.value = selectedAction;
    const query = overlay.querySelector("#history-search").value.trim().toLocaleLowerCase();
    const filtered = entries.filter((entry) => {
      const searchable = `${entry.action || ""} ${entry.message || ""} ${localize(entry.message || "")}`.toLocaleLowerCase();
      return (!query || searchable.includes(query)) && (!actionSelect.value || entry.action === actionSelect.value);
    });
    if (!filtered.length) {
      list.innerHTML = `<p class="history-empty">${text("Nenhuma alteração registrada ainda.", "No changes recorded yet.")}</p>`;
      return;
    }
    list.innerHTML = filtered.map((entry) => {
      const date = new Date(entry.at);
      const when = Number.isNaN(date.getTime()) ? text("Data não disponível", "Date unavailable") : date.toLocaleString(english ? "en-US" : "pt-BR");
      const message = localize(entry.message || text("Alteração no catálogo", "Catalog change"));
      return `<article class="history-row"><span class="history-action">${escapeHtml((entry.action || text("alteração", "change")).replaceAll("_", " "))}</span><div><b>${escapeHtml(message)}</b><small>${escapeHtml(when)}</small></div></article>`;
    }).join("");
  };
  overlay.querySelector("#history-clear").onclick = async () => {
    if (!confirm("Limpar todo o histórico de alterações?")) return;
    await api().clear_activity_log();
    await renderHistory();
  };
  overlay.querySelector("#history-clear-old").onclick = async () => {
    if (!confirm("Remover entradas do histórico anteriores a 30 dias?")) return;
    const result = await api().clear_old_activity_log(30);
    if (!result?.ok) alert(result?.error || "Não foi possível limpar as entradas antigas.");
    await renderHistory();
  };
  overlay.querySelector("#history-search").oninput = renderHistory;
  overlay.querySelector("#history-action").onchange = renderHistory;
  await renderHistory();
}
document.getElementById("btn-history").onclick = openHistory;

document.getElementById("btn-launch-game").onclick = async () => {
  const button = document.getElementById("btn-launch-game");
  button.disabled = true;
  try {
    const result = await api().launch_game();
    if (!result?.ok) alert(result?.error || "Não foi possível abrir o jogo.");
  } finally {
    window.setTimeout(() => { button.disabled = false; }, 1000);
  }
};

function openShortcuts() {
  document.getElementById("shortcuts-overlay")?.remove();
  const overlay = document.createElement("div");
  overlay.id = "shortcuts-overlay";
  overlay.className = "modal-overlay open";
  const rows = [
    ["Ctrl + F", "Focar a busca"],
    ["Ctrl + Shift + R", "Atualizar a lista de mods"],
    ["Ctrl + E", "Ativar/desativar todos os mods selecionados"],
    ["F2", "Renomear o mod destacado"],
    ["↑ ↓ ← → / WASD", "Navegar pela lista de mods"],
    ["Setas ou WASD", "Nos Backgrounds, selecionar a prévia de cinematic anterior/próxima"],
    ["Enter", "Abrir detalhes do mod destacado"],
    ["Shift + clique", "Selecionar o intervalo desde o último mod marcado"],
    ["Esc", "Fechar detalhes, janela ou menu aberto"],
    ["F1", "Mostrar esta ajuda"],
  ];
  overlay.innerHTML = `<section class="shortcuts-dialog" role="dialog" aria-modal="true"><header><b>⌨ Keyboard Shortcuts</b><button class="icon-btn" aria-label="Fechar">✕</button></header><div class="shortcuts-body">${rows.map(([keys, label]) => `<div><kbd>${keys}</kbd><span>${label}</span></div>`).join("")}</div><footer><button class="btn" id="shortcuts-close">Fechar</button></footer></section>`;
  const close = () => overlay.remove();
  overlay.querySelector("header button").onclick = close;
  overlay.querySelector("#shortcuts-close").onclick = close;
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  document.body.appendChild(overlay);
}
document.getElementById("btn-shortcuts").onclick = openShortcuts;

function activateCinematicPreview(index, scroll = true, focus = true) {
  const previews = [...document.querySelectorAll("#mod-detail-content .cinematic-preview")];
  if (!previews.length) return;
  const nextIndex = Math.max(0, Math.min(previews.length - 1, index));
  state.cinematicPreviewIndex = nextIndex;
  previews.forEach((preview, previewIndex) => {
    const active = previewIndex === nextIndex;
    preview.classList.toggle("is-keyboard-active", active);
    preview.closest(".cinematic-card")?.classList.toggle("has-keyboard-preview", active);
  });
  const preview = previews[nextIndex];
  if (focus) preview.focus({ preventScroll: true });
  if (scroll) preview.scrollIntoView({ block: "nearest", behavior: "auto" });
}

function navigateCinematicPreviews(direction) {
  const previewCount = document.querySelectorAll("#mod-detail-content .cinematic-preview").length;
  if (!previewCount) return;
  const nextIndex = (state.cinematicPreviewIndex + direction + previewCount) % previewCount;
  activateCinematicPreview(nextIndex);
}

async function renameModPrompt(mod) {
  if (!mod) return;
  const newName = prompt("Novo nome:", mod.name);
  if (!newName || !newName.trim() || newName.trim() === mod.name) return;
  const result = await api().rename_mod(mod.id, newName.trim());
  if (result?.ok) {
    mod.name = newName.trim();
    renderLocalChange();
  } else {
    alert(result?.error || "Não foi possível renomear o mod.");
  }
}

let modNavigationFrame = 0;
function scheduleKeyboardModFocus() {
  if (modNavigationFrame) return;
  modNavigationFrame = requestAnimationFrame(() => {
    modNavigationFrame = 0;
    document.querySelectorAll(".mod-card.keyboard-focused").forEach((card) => card.classList.remove("keyboard-focused"));
    const card = document.querySelector(`.mod-card[data-id="${state.focusedModId}"]`);
    if (!card) return;
    card.classList.add("keyboard-focused");
    card.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
  });
}

document.addEventListener("keydown", async (event) => {
  const target = event.target;
  const editing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target?.isContentEditable;
  const componentDialog = document.getElementById("component-diagnostic-overlay");
  if (componentDialog) {
    if (event.key === "Escape") { event.preventDefault(); componentDialog.querySelector(".dialog-close")?.click(); }
    return;
  }
  if (state.importBusy || state.installCancelling) return;
  if (event.key === "F1") {
    event.preventDefault();
    openShortcuts();
    return;
  }
  if (event.key === "Escape") {
    if (document.getElementById("gallery-viewer")) {
      closeGalleryViewer();
      return;
    }
    const audioPicker = document.getElementById("audio-picker");
    if (audioPicker && !audioPicker.hidden) {
      audioPicker.hidden = true;
      return;
    }
    // Fecha apenas a camada visual que está por cima. Um segundo Esc fecha a próxima.
    const closeDynamicOverlay = [
      "mod-conflict-details-overlay", "conflicts-overlay", "identity-correction-overlay",
      "create-component-label-overlay", "create-tag-overlay", "gallery-image-menu",
      "component-label-menu", "assign-tag-menu", "shortcuts-overlay", "profiles-overlay", "history-overlay",
    ].map((id) => document.getElementById(id)).find(Boolean);
    if (closeDynamicOverlay) {
      closeDynamicOverlay.remove();
      return;
    }
    if (ctxMenu?.classList.contains("open")) {
      ctxMenu.classList.remove("open");
      document.querySelectorAll(".ctx-submenu").forEach((menu) => menu.remove());
      return;
    }
    if (addModOverlay?.classList.contains("open")) {
      await cancelPendingInstall();
      return;
    }
    if (settingsOverlay?.classList.contains("open")) {
      closeSettings();
      return;
    }
    if (document.getElementById("mod-detail-overlay")?.classList.contains("open")) {
      closeModDetailsPage();
      return;
    }
    return;
  }
  if (editing) return;

  const detailOpen = document.getElementById("mod-detail-overlay")?.classList.contains("open");
  if (detailOpen) {
    const audioPickerOpen = !document.getElementById("audio-picker")?.hidden;
    const key = String(event.key || "").toLowerCase();
    if (!audioPickerOpen && document.querySelector("#mod-detail-content .cinematic-section") && ["arrowup", "arrowleft", "w", "a", "arrowdown", "arrowright", "s", "d"].includes(key)) {
      event.preventDefault();
      navigateCinematicPreviews(["arrowup", "arrowleft", "w", "a"].includes(key) ? -1 : 1);
    }
    return;
  }

  const visibleMods = filteredMods();
  const focusedIndex = visibleMods.findIndex((mod) => mod.id === state.focusedModId);
  const focusMod = (index) => {
    if (!visibleMods.length) return null;
    const nextIndex = Math.max(0, Math.min(visibleMods.length - 1, index));
    const mod = visibleMods[nextIndex];
    state.focusedModId = mod.id;
    scheduleKeyboardModFocus();
    return mod;
  };

  const navigationKey = String(event.key || "").toLowerCase();
  const arrowNavigation = ["arrowup", "arrowleft", "arrowdown", "arrowright"].includes(navigationKey);
  const wasdNavigation = !event.ctrlKey && !event.altKey && !event.metaKey && ["w", "a", "s", "d"].includes(navigationKey);
  if (arrowNavigation || wasdNavigation) {
    event.preventDefault();
    const direction = ["arrowup", "arrowleft", "w", "a"].includes(navigationKey) ? -1 : 1;
    let start = focusedIndex;
    if (start < 0 && state.lastSelectedModId) start = visibleMods.findIndex((mod) => mod.id === state.lastSelectedModId);
    if (start < 0) start = direction > 0 ? -1 : visibleMods.length;
    state.keyboardNavigation = true;
    focusMod(Math.max(0, start) + direction);
    return;
  }
  if (event.key === "Enter") {
    const mod = visibleMods.find((item) => item.id === state.focusedModId);
    if (mod && state.keyboardNavigation) {
      event.preventDefault();
      showModDetailsPage(mod.id);
    }
    return;
  }
  if (event.key === "F2") {
    const mod = visibleMods.find((item) => item.id === state.focusedModId)
      || (state.selectedModIds.size === 1 ? state.mods.find((item) => state.selectedModIds.has(item.id)) : null);
    if (mod) {
      event.preventDefault();
      await renameModPrompt(mod);
    }
    return;
  }
  if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === "f") {
    event.preventDefault();
    document.getElementById("search-input").focus();
  } else if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "r") {
    event.preventDefault();
    await reloadAll();
  } else if (event.ctrlKey && !event.shiftKey && event.key.toLowerCase() === "e") {
    event.preventDefault();
    const selectedMods = state.mods.filter((mod) => state.selectedModIds.has(mod.id));
    if (!selectedMods.length) return;
    for (const mod of selectedMods) {
      const result = await api().toggle_mod(mod.id);
      if (!result?.ok) {
        alert(result?.error || `Não foi possível alterar "${mod.name}".`);
        break;
      }
    }
    await reloadAll();
  }
});

function showConflictResults(result) {
  state.visibleConflictReport = result;
  result = currentConflictReport(result);
  document.getElementById("conflicts-overlay")?.remove();
  const conflicts = result.conflicts || [];
  const overlay = document.createElement("div");
  overlay.id = "conflicts-overlay";
  const rows = conflicts.map((conflict) => {
    const owners = conflict.owners.map((owner) => {
      return `<li><b>${escapeHtml(owner.mod)}</b> · ${escapeHtml(owner.component)}</li>`;
    }).join("");
    const verdict = `<span class="conflict-tie">⚠ Escolha o que manter ou desative um dos mods concorrentes.</span>`;
    const label = conflict.kind === "manual" ? "Marcado manualmente" : "Asset interno sobreposto";
    return `<article class="conflict-row has-tie"><div class="conflict-row-status">${label} · ativo agora</div><div class="conflict-asset"><b>${escapeHtml(conflict.asset_type)}</b><code>${escapeHtml(conflict.asset_path)}</code></div><ul>${owners}</ul>${verdict}</article>`;
  }).join("");
  const unreadable = result.unreadable?.length
    ? `<p class="conflict-note">${result.unreadable.length} componente(s) não puderam ser lidos e não entraram no resultado.</p>` : "";
  const summary = conflicts.length
    ? `<div class="conflict-summary"><span>${conflicts.length} conflito(s) ativo(s)</span></div>`
    : "";
  overlay.innerHTML = `<section class="conflicts-dialog" role="dialog" aria-modal="true"><header><div><b>Verificar conflitos</b><small>${result.checked_components || 0} componente(s) analisado(s) · ${result.ignored_physics_components || 0} Physics ignorado(s)</small></div><button class="icon-btn" aria-label="Fechar">✕</button></header><div class="conflicts-body">${summary}${conflicts.length ? rows : `<div class="conflict-empty">Nenhum asset interno é sobrescrito por dois componentes ativos.</div>`}${unreadable}</div><footer><button class="btn" id="conflicts-close">Fechar</button></footer></section>`;
  const close = () => { state.visibleConflictReport = null; overlay.remove(); };
  overlay.querySelector("header button").onclick = close;
  overlay.querySelector("#conflicts-close").onclick = close;
  if (conflicts.length) {
    const resolve = document.createElement("button");
    resolve.className = "btn";
    resolve.textContent = "Escolher o que manter…";
    resolve.onclick = () => void showConflictResolver(result);
    overlay.querySelector("footer").prepend(resolve);
  }
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  document.body.appendChild(overlay);
}

function currentConflictReport(result) {
  const mods = new Map(state.mods.map(mod => [mod.id, mod]));
  const conflicts = (result.conflicts || []).flatMap(conflict => {
    const owners = (conflict.owners || []).flatMap(owner => {
      const mod = mods.get(owner.mod_id);
      if (!mod?.enabled) return [];
      const manual = conflict.kind === "manual";
      const components = mod.components || [];
      const index = components.findIndex(component => component.id === owner.component_id);
      if (!manual && components.length && (index < 0 || components[index].enabled === false)) return [];
      // Não reinterpretamos identidade alterada usando um relatório antigo.
      if (!manual && (owner.character !== mod.character || owner.skin !== (mod.skin || ""))) return [];
      const component = components[index];
      const label = String(component?.description || "").trim().toLowerCase();
      return [{...owner, mod: mod.name || owner.mod, priority: Math.max(1, Math.min(10, Number(mod.priority) || 1)),
        is_primary: component ? label === "principal" || (!label && index === 0) : owner.is_primary}];
    });
    // Filtra apenas as disputas já encontradas pelo backend, preservando sua
    // política de Principal e de personagem/skin. Um acompanhamento sozinho
    // não pode virar conflito interno quando o outro mod é desligado.
    const overlap = (left, right) => conflict.kind === "manual"
      ? left.mod_id !== right.mod_id
      : left.mod_id === right.mod_id ? left.is_primary && right.is_primary
        : left.character && left.skin && left.character.toLowerCase() === right.character.toLowerCase()
          && left.skin.toLowerCase() === right.skin.toLowerCase();
    const active = owners.filter((owner, index) => owners.some((other, otherIndex) => index !== otherIndex && overlap(owner, other)));
    if (active.length < 2) return [];
    active.sort((a, b) => b.priority - a.priority || a.mod.localeCompare(b.mod));
    const tie = active.filter(owner => owner.priority === active[0].priority).length > 1;
    return [{...conflict, owners: active, tie, winner: tie ? null : active[0], resolution: tie ? "tie" : "priority_preference"}];
  });
  return {...result, conflicts, tied_conflicts: conflicts.filter(conflict => conflict.tie).length,
    resolved_conflicts: conflicts.filter(conflict => !conflict.tie).length};
}

function cacheConflictIndicators(conflicts, { replace = true } = {}) {
  state.conflictCheckPerformed = true;
  state.conflictRecords = replace ? (conflicts || []) : [...state.conflictRecords, ...(conflicts || [])];
  rebuildConflictIndicators();
}

function rebuildConflictIndicators() {
  state.conflictsByMod.clear();
  currentConflictReport({conflicts: state.conflictRecords || []}).conflicts.forEach((conflict) => {
    const owners = conflict.owners || [];
    const uniqueOwners = [...new Map(owners.map(owner => [owner.mod_id, owner])).values()];
    uniqueOwners.forEach((owner) => {
      if (!owner.mod_id) return;
      const entry = state.conflictsByMod.get(owner.mod_id) || { count: 0, resolvedByPriority: 0, ties: 0, wins: 0, opponents: new Map() };
      entry.count += 1;
      if (conflict.tie) entry.ties += 1;
      else {
        entry.resolvedByPriority += 1;
        if (conflict.winner?.mod_id === owner.mod_id) entry.wins += 1;
      }
      uniqueOwners.filter((other) => other.mod_id && other.mod_id !== owner.mod_id).forEach((other) => {
        const previous = entry.opponents.get(other.mod_id) || { name: other.mod || "Mod", assets: 0 };
        previous.assets += 1;
        entry.opponents.set(other.mod_id, previous);
      });
      state.conflictsByMod.set(owner.mod_id, entry);
    });
  });
  const popup = document.getElementById("mod-conflict-details-overlay");
  if (popup) showModConflictDetails(state.mods.find(mod => mod.id === popup.dataset.modId));
  if (document.getElementById("conflicts-overlay") && state.visibleConflictReport) {
    showConflictResults({...state.visibleConflictReport, conflicts: state.conflictRecords});
  }
}

function conflictRequestSnapshot() {
  return {revision: state.conflictRevision, serial: ++state.conflictRequestSerial};
}

function isCurrentConflictRequest(request) {
  return request.revision === state.conflictRevision && request.serial === state.conflictRequestSerial;
}

function queueConflictRefresh() {
  clearTimeout(state.conflictRefreshTimer);
  state.conflictRefreshTimer = setTimeout(() => { void refreshConflictIndicators(); }, 180);
}

function scheduleConflictRefresh() {
  state.conflictRevision += 1;
  rebuildConflictIndicators();
  // Só recalculamos automaticamente depois que o usuário já rodou ao menos
  // uma checagem; assim abrir o programa não dispara uma leitura pesada.
  if (!state.conflictCheckPerformed) return;
  state.conflictRefreshPending = true;
  queueConflictRefresh();
}

async function refreshConflictIndicators() {
  if (state.conflictRefreshInProgress || state.conflictManualCheckInProgress) {
    state.conflictRefreshPending = true;
    return;
  }
  clearTimeout(state.conflictRefreshTimer);
  state.conflictRefreshPending = false;
  state.conflictCheckPerformed = true;
  state.conflictRefreshInProgress = true;
  const request = conflictRequestSnapshot();
  try {
    const result = await api().get_conflicts();
    if (!isCurrentConflictRequest(request)) {
      state.conflictRefreshPending = true;
      return;
    }
    if (!result?.ok) {
      if (state.conflictShowResultsPending) {
        state.conflictShowResultsPending = false;
        alert(result?.error || "Não foi possível atualizar os conflitos.");
      }
      return;
    }
    cacheConflictIndicators(result.conflicts, { replace: true });
    renderMods();
    if (state.conflictShowResultsPending) {
      state.conflictShowResultsPending = false;
      showConflictResults(result);
    }
    return result;
  } catch (error) {
    // Conserva apenas conflitos ainda possíveis entre os responsáveis ativos.
    rebuildConflictIndicators();
    if (state.conflictShowResultsPending) {
      state.conflictShowResultsPending = false;
      alert(error.message || "Não foi possível atualizar os conflitos.");
    }
  } finally {
    state.conflictRefreshInProgress = false;
    if (state.conflictRefreshPending) queueConflictRefresh();
  }
}

function showModConflictDetails(mod) {
  document.getElementById("mod-conflict-details-overlay")?.remove();
  mod = state.mods.find(item => item.id === mod?.id);
  const info = mod?.enabled && state.conflictsByMod.get(mod.id);
  if (!info) return;
  const opponents = [...(info?.opponents?.entries() || [])]
    .map(([id, opponent]) => ({...opponent, id}))
    .sort((a, b) => b.assets - a.assets || a.name.localeCompare(b.name));
  const overlay = document.createElement("div");
  overlay.id = "mod-conflict-details-overlay";
  overlay.dataset.modId = mod.id;
  overlay.className = "mod-conflict-details-overlay";
  const priorityStatus = `<p class="conflict-tie">Escolha o que manter ou desative um dos mods concorrentes. O CrabVault não controla a ordem de carregamento do jogo.</p>`;
  overlay.innerHTML = `<section class="mod-conflict-details-dialog" role="dialog" aria-modal="true"><header><div><b>⚠ Conflitos de compatibilidade</b><small>${escapeHtml(mod.name)}</small></div><button class="icon-btn" aria-label="Fechar">✕</button></header><div class="mod-conflict-details-body"><p>Este mod sobrescreve ${info?.count || 0} asset(s) também alterado(s) por:</p>${priorityStatus}<ul>${opponents.map((opponent, index) => `<li><div class="mod-conflict-opponent"><b>${escapeHtml(opponent.name)}</b><span>${opponent.assets} asset(s) em comum</span></div><button class="btn conflict-disable-opponent" data-opponent-index="${index}" title="Desativar este mod concorrente">Desativar mod</button></li>`).join("") || "<li>Nenhum outro mod ativo identificado.</li>"}</ul><p class="mod-conflict-action-note">O mod deste alerta continuará ativo.</p></div><footer><button class="btn" id="mod-conflict-details-close">Fechar</button></footer></section>`;
  const close = () => overlay.remove();
  overlay.querySelector("header button").onclick = close;
  overlay.querySelector("#mod-conflict-details-close").onclick = close;
  overlay.querySelectorAll(".conflict-disable-opponent").forEach((button) => {
    button.onclick = async () => {
      const opponent = opponents[Number(button.dataset.opponentIndex)];
      if (!opponent) return;
      button.disabled = true;
      button.textContent = "Desativando…";
      try {
        const result = await api().set_mods_enabled([opponent.id], false);
        const changed = new Set(result?.changed || []);
        if (!result?.ok && !changed.has(opponent.id)) {
          throw new Error(result?.error || result?.errors?.[0]?.error || "Não foi possível desativar o mod concorrente.");
        }
        const currentOpponent = state.mods.find(item => item.id === opponent.id);
        if (currentOpponent) currentOpponent.enabled = false;
        renderLocalChange();
      } catch (error) {
        alert(error?.message || "Não foi possível desativar o mod concorrente.");
        button.disabled = false;
        button.textContent = "Desativar mod";
      }
    };
  });
  overlay.onclick = (event) => { if (event.target === overlay) close(); };
  document.body.appendChild(overlay);
}

document.getElementById("btn-conflicts").onclick = async () => {
  const button = document.getElementById("btn-conflicts");
  button.disabled = true;
  button.textContent = "Verificando…";
  state.conflictManualCheckInProgress = true;
  state.conflictShowResultsPending = false;
  state.conflictCheckPerformed = true;
  const request = conflictRequestSnapshot();
  try {
    const requestId = newOperationRequest("conflicts");
    const result = await runImportOperation(() => api().start_conflict_check(requestId), "Verificando conflitos",
      { requestId, context: { kind: "conflicts" } });
    if (result?.cancelled) return;
    if (!result?.ok) alert(result?.error || "Não foi possível verificar conflitos.");
    else if (isCurrentConflictRequest(request)) {
      cacheConflictIndicators(result.conflicts, { replace: true });
      renderMods();
      showConflictResults(result);
    } else {
      state.conflictRefreshPending = true;
      state.conflictShowResultsPending = true;
    }
  } catch (error) { alert(error.message); }
  finally {
    state.conflictManualCheckInProgress = false;
    if (state.conflictRefreshPending) queueConflictRefresh();
    button.disabled = false;
    button.textContent = "⚠ Verificar conflitos";
  }
};

document.getElementById("btn-scan-mods").onclick = async () => {
  const button = document.getElementById("btn-scan-mods");
  const status = document.getElementById("scan-status");
  const english = normalizedLanguage(state.settings.ui_language) === "en";
  const firstScan = state.settings.installed_scan_completed !== true;
  button.disabled = true;
  button.textContent = english ? "Scanning…" : "Buscando…";
  status.hidden = false;
  status.textContent = firstScan
    ? (english
      ? "First scan: CrabVault is reading the installed packages to identify their types. This can take a while in a large library; later scans reuse the saved analysis."
      : "Primeiro scan: o CrabVault está lendo os pacotes instalados para identificar seus tipos. Isso pode levar um tempo em uma biblioteca grande; os próximos scans reutilizam a análise salva.")
    : (english ? "Scanning installed mods and analyzing new or changed packages…" : "Buscando mods instalados e analisando pacotes novos ou alterados…");
  try {
    const result = await api().scan_installed_mods();
    if (!result.ok) alert(result.error);
    else {
      if (result.scan_completed) state.settings.installed_scan_completed = true;
      await reloadAll();
      const summary = [];
      if (result.added) summary.push(english ? `${result.added} new mod(s) added` : `${result.added} mod(s) novo(s) adicionado(s)`);
      if (result.classified) summary.push(english ? `${result.classified} mod(s) classified` : `${result.classified} mod(s) classificado(s)`);
      if (result.identified) summary.push(english ? `${result.identified} skin identity/identities detected` : `${result.identified} identidade(s) de skin detectada(s)`);
      if (result.reclassified) summary.push(english ? `${result.reclassified} mod(s) reclassified` : `${result.reclassified} mod(s) reclassificado(s)`);
      if (result.skipped_nested) summary.push(english ? `${result.skipped_nested} variation subfolder(s) ignored` : `${result.skipped_nested} subpasta(s) de variação ignorada(s)`);
      alert(summary.length ? `${summary.join(english ? " and " : " e ")}.` : (english
        ? "No new mods found. Previously detected mods are not duplicated."
        : "Nenhum mod novo encontrado. Os mods já detectados não são duplicados."));
    }
  } finally {
    status.hidden = true;
    button.disabled = false;
    button.textContent = english ? "Scan installed mods" : "Buscar mods instalados";
  }
};

document.getElementById("btn-auto-detect").onclick = async () => {
  const statusEl = document.getElementById("auto-detect-status");
  statusEl.textContent = "Procurando nas bibliotecas do Steam...";
  const path = await api().auto_detect_mods_path();
  if (path) {
    document.getElementById("settings-mods-path").value = path;
    state.settings.mods_path = path;
    statusEl.textContent = "Encontrado!";
    await reloadFolders();
  } else {
    statusEl.textContent = "Não consegui achar automaticamente. Usa o Browse pra apontar manualmente.";
  }
};

document.getElementById("btn-browse-folder").onclick = async () => {
  const path = await api().set_mods_path_dialog();
  if (path) {
    document.getElementById("settings-mods-path").value = path;
    state.settings.mods_path = path;
    await reloadFolders();
  }
};

// ---------------------------------------------------------
// Reload helpers
// ---------------------------------------------------------
async function reloadFolders() {
  state.folders = await api().get_folders();
}

function safeRender(fn) {
  try {
    fn();
  } catch (err) {
    console.error(`Erro ao renderizar (${fn.name}):`, err);
  }
}

async function reloadAll() {
  if (typeof detailMetadataCache !== "undefined") detailMetadataCache.clear();
  renderMods.cardCache?.clear();
  const snapshot = await api().get_library_snapshot();
  const previousMods = new Map(state.mods.map((mod) => [mod.id, mod]));
  [state.mods, state.characters, state.types, state.tags, state.folders] =
    [snapshot.mods.map((mod) => preserveModThumbnail(mod, previousMods.get(mod.id))),
     snapshot.characters, snapshot.types, snapshot.tags, snapshot.folders];
  if (state.activeCharacter) await loadCharacterSkins(state.activeCharacter);
  scheduleConflictRefresh();

  safeRender(renderCharacters);
  safeRender(renderTypes);
  safeRender(renderTags);
  safeRender(renderMods);
  safeRender(renderHeaderCount);
}

function formatGithubDownloads(value) {
  return new Intl.NumberFormat(normalizedLanguage(state.settings.ui_language) === "en" ? "en-US" : "pt-BR", {
    notation: Number(value) >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(Math.max(0, Number(value) || 0));
}

async function loadGithubDownloadStats() {
  const badge = document.getElementById("github-downloads");
  const count = document.getElementById("github-download-count");
  if (!badge || !count) return;
  try {
    const result = await api().get_github_download_stats();
    if (!result?.ok) return;
    count.textContent = formatGithubDownloads(result.downloads);
    badge.title = normalizedLanguage(state.settings.ui_language) === "en"
      ? "Installer downloads on GitHub (not unique users)"
      : "Downloads dos instaladores no GitHub (não são usuários únicos)";
    badge.hidden = false;
  } catch (_) {
    badge.hidden = true;
  }
}

// ---------------------------------------------------------
// Init
// ---------------------------------------------------------
async function init() {
  state.settings = await api().get_settings();
  window.setUiLanguage?.(state.settings.ui_language);
  applyAccentColor(state.settings.accent_color);
  applyThemeMode(state.settings.theme_mode);
  applyPreviewVolume();
  setViewMode(state.settings.view_mode, { render: false });
  state.roster = await api().get_character_roster();
  // A varredura usa UAssetTool e pode levar vários segundos em bibliotecas
  // grandes. Ela continua disponível em "Scan installed mods", sem atrasar
  // a primeira renderização da tela principal.
  await reloadAll();
  void loadGithubDownloadStats();
  if (typeof refreshOperationNotice === "function") void refreshOperationNotice();
  if (state.settings.language_selected !== true) openLanguageSelection();
  else if (state.settings.tutorial_completed !== true) openTutorial(state.settings.ui_language);
}

const volumeButton = document.getElementById("btn-volume");
const volumePopover = document.getElementById("volume-popover");
const volumeInput = document.getElementById("preview-volume");
volumeButton?.addEventListener("click", (event) => { event.stopPropagation(); volumePopover.hidden = !volumePopover.hidden; });
volumeInput?.addEventListener("input", () => {
  state.settings.preview_volume = Number(volumeInput.value) / 100;
  applyPreviewVolume();
});
volumeInput?.addEventListener("change", async () => {
  state.settings = await api().save_settings({ preview_volume: state.settings.preview_volume });
  applyPreviewVolume();
});
document.addEventListener("click", (event) => { if (!document.getElementById("volume-control")?.contains(event.target)) volumePopover.hidden = true; });

window.addEventListener("pywebviewready", init);
