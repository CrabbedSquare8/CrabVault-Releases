// Tradução offline da interface. Português é o texto-fonte canônico.
(() => {
  "use strict";

  const en = new Map(Object.entries({
    "Abrir Marvel Rivals pelo Steam": "Open Marvel Rivals through Steam",
    "▶ Abrir jogo": "▶ Open game",
    "Salvar e aplicar perfis de mods": "Save and apply mod profiles",
    "Perfis": "Profiles",
    "Ver alterações recentes": "View recent changes",
    "Histórico": "History",
    "Instalar um ReShade em Binaries\\Win64": "Install ReShade in Binaries\\Win64",
    "Instalar cinemáticas em Content\\Marvel": "Install cinematics in Content\\Marvel",
    "Volume das prévias": "Preview volume",
    "Atalhos de teclado (F1)": "Keyboard shortcuts (F1)",
    "Configurações": "Settings",
    "Downloads dos instaladores no GitHub": "Installer downloads on GitHub",
    "Revisar": "Review",
    "Buscar mods instalados...": "Search installed mods...",
    "Mais recentes": "Newest",
    "Mais antigos": "Oldest",
    "🏷 Todas as tags": "🏷 All tags",
    "FILTROS": "FILTERS",
    "Personagens": "Characters",
    "Tipos": "Types",
    "Pastas": "Folders",
    "Nova pasta": "New folder",
    "📚 Todos os mods": "📚 All mods",
    "Todos os mods": "All mods",
    "selecionados": "selected",
    "Ativar mods selecionados": "Enable selected mods",
    "Desativar mods selecionados": "Disable selected mods",
    "Ativar": "Enable",
    "Desativar": "Disable",
    "Marcar manualmente conflito entre os mods ativos selecionados": "Manually mark a conflict between selected active mods",
    "⚠ Marcar conflito": "⚠ Mark conflict",
    "Limpar seleção": "Clear selection",
    "⚠ Verificar conflitos": "⚠ Check conflicts",
    "Detectar mods já instalados": "Detect already installed mods",
    "Buscar mods instalados": "Scan installed mods",
    "Visualização em grade": "Grid view",
    "Visualização em lista": "List view",
    "Atualizar": "Refresh",
    "Detalhes do mod": "Mod details",
    "Selecione um mod para ver os detalhes.": "Select a mod to view its details.",
    "‹  Voltar aos mods": "‹  Back to mods",
    "Fechar detalhes": "Close details",
    "Instalar mods": "Install mods",
    "Nome personalizado": "Custom name",
    "Correções pessoais salvas (opcional)": "Saved personal corrections (optional)",
    "Não reutilizar correções": "Do not reuse corrections",
    "Personagem": "Character",
    "Buscar personagem...": "Search character...",
    "Nome de uma nova skin...": "New skin name...",
    "Link do mod (opcional)": "Mod link (optional)",
    "Pasta de instalação": "Installation folder",
    "Adicionar imagens": "Add images",
    "Adicionar imagem": "Add image",
    "Adicionar uma imagem de capa": "Add a cover image",
    "Escolher imagem de capa": "Choose cover image",
    "Ofuscação": "Obfuscation",
    "Criptografar mod para bloquear extração": "Encrypt the mod to block extraction",
    "IoStore híbrido": "Hybrid IoStore",
    "Requer assets brutos e processados": "Requires raw and processed assets",
    "Formato PAK legado": "Legacy PAK format",
    "Para mods de áudio/configuração": "For audio/configuration mods",
    "Os tipos são detectados pelos arquivos selecionados. As variações ficam guardadas na biblioteca e podem ser alternadas nos detalhes do mod.": "Types are detected from the selected files. Variations remain in the library and can be switched from mod details.",
    "📁  Instalar em": "📁  Install to",
    "Cancelar": "Cancel",
    "Instalar mod": "Install mod",
    "Pasta de mods do jogo": "Game mods folder",
    "Nenhuma pasta configurada ainda": "No folder configured yet",
    "✨ Detectar automaticamente": "✨ Detect automatically",
    "📁 Escolher pasta": "📁 Choose folder",
    "VISUALIZADOR 3D INTEGRADO": "BUILT-IN 3D VIEWER",
    "Sem FModel ou instalação de .NET. Na primeira abertura, o Manager baixa os arquivos de leitura necessários; depois reutiliza a cópia local. A pasta do jogo continua necessária.": "No FModel or .NET installation. On first use, the Manager downloads the required reader files and then reuses the local copy. The game folder is still required.",
    "Sem FModel ou instalação de .NET. Na primeira abertura, o CrabVault baixa e verifica o mapping, zlib e Oodle 2.9.10. A Oodle vem do projeto comunitário": "No FModel or .NET installation. On first use, CrabVault downloads and verifies the mapping, zlib, and Oodle 2.9.10. Oodle comes from the community project",
    "sob os termos da Unreal Engine; depois tudo é reutilizado localmente.": "under the Unreal Engine terms; everything is then reused locally.",
    "Preparar / atualizar suporte 3D": "Prepare / update 3D support",
    "VISUALIZAÇÃO DOS MODS": "MOD DISPLAY",
    "Ocultar sufixo _9999999_P nos nomes dos mods": "Hide the _9999999_P suffix in mod names",
    "Ocultar sufixo": "Hide suffix",
    "nos nomes dos mods": "from mod names",
    "Abrir detalhes automaticamente ao clicar": "Open details automatically on click",
    "Mostrar badge de tipo nos cards": "Show type badge on cards",
    "IDIOMA / LANGUAGE": "LANGUAGE / IDIOMA",
    "Português": "Portuguese",
    "Define o idioma de toda a interface do CrabVault.": "Sets the language for the entire CrabVault interface.",
    "Rever tutorial": "Review tutorial",
    "CATÁLOGO DE PERSONAGENS E SKINS": "CHARACTER AND SKIN CATALOG",
    "Verifica uma vez por dia os IDs mantidos em": "Checks once a day for IDs maintained at",
    "O catálogo incluído continua funcionando offline e os ícones existentes do Manager são preservados.": "The bundled catalog keeps working offline, and the Manager's existing icons are preserved.",
    "Verifica uma vez por dia os IDs mantidos em donutman07/MarvelRivalsCharacterIDs. O catálogo incluído continua funcionando offline e os ícones existentes do Manager são preservados.": "Checks the IDs maintained at donutman07/MarvelRivalsCharacterIDs once a day. The bundled catalog keeps working offline, and the Manager's existing icons are preserved.",
    "Atualizar catálogo agora": "Update catalog now",
    "ARQUIVOS DA IMPORTAÇÃO": "IMPORT FILES",
    "Guardar uma cópia compactada na biblioteca": "Keep an archive copy in the library",
    "Preserva o ZIP/RAR/7z original. Se você selecionar PAK/UCAS/UTOC soltos, reúne todos eles em um novo ZIP dentro de mods_storage.": "Keeps the original ZIP/RAR/7z. If you select loose PAK/UCAS/UTOC files, all of them are collected into a new ZIP inside mods_storage.",
    "Preserva o ZIP/RAR/7z original. Se você selecionar PAK/UCAS/UTOC soltos, reúne todos eles em um novo ZIP dentro de": "Keeps the original ZIP/RAR/7z. If you select loose PAK/UCAS/UTOC files, all of them are collected into a new ZIP inside",
    "Apagar os arquivos originais depois de instalar": "Delete original files after installation",
    "Somente após sucesso, remove do local de origem ZIP/RAR/7z, PAK/UCAS/UTOC e imagens escolhidas. Desmarque para mantê-los onde estão.": "Only after success, removes ZIP/RAR/7z, PAK/UCAS/UTOC, and selected images from their source location. Uncheck to keep them there.",
    "OPÇÕES AVANÇADAS": "ADVANCED OPTIONS",
    "Ignorar bloqueio de operações enquanto o jogo estiver aberto": "Bypass operation lock while the game is running",
    "Quando desativado, instalar, mover, ativar ou desativar mods é bloqueado enquanto Marvel Rivals estiver em execução.": "When disabled, installing, moving, enabling, or disabling mods is blocked while Marvel Rivals is running.",
    "MANUTENÇÃO DA BIBLIOTECA": "LIBRARY MAINTENANCE",
    "Verificações sob demanda. Reparos e recuperações só são aplicados após sua revisão.": "On-demand checks. Repairs and recoveries are applied only after your review.",
    "Verificar integridade": "Check integrity",
    "Classificações pendentes": "Pending classifications",
    "Operações interrompidas": "Interrupted operations",
    "Comparar o conteúdo dos arquivos (pode levar mais tempo)": "Compare file contents (may take longer)",
    "BACKUP DO CATÁLOGO": "CATALOG BACKUP",
    "⇩ Criar backup": "⇩ Create backup",
    "⇧ Restaurar backup": "⇧ Restore backup",
    "BACKUP COMPLETO": "FULL BACKUP",
    "Criar backup completo…": "Create full backup…",
    "Extrair backup completo…": "Extract full backup…",
    "APARÊNCIA": "APPEARANCE",
    "Tema escuro": "Dark theme",
    "Tema claro": "Light theme",
    "Cor de destaque para botões, seleção e indicadores.": "Accent color for buttons, selection, and indicators.",
    "Vermelho": "Red", "Azul": "Blue", "Roxo": "Purple", "Verde": "Green", "Dourado": "Gold",
    "Salvar": "Save",
    "Adicionar tag...": "Add tag...", "Adicionar tag…": "Add tag…", "Mover para...": "Move to...", "Mover para…": "Move to…", "Renomear": "Rename",
    "Editar imagem": "Edit image", "Abrir no Explorador": "Open in File Explorer", "Copiar caminho": "Copy path",
    "Remover mod": "Remove mod",
    "Remover mod (preserva imagens e ZIP/RAR/7z)": "Remove mod (keeps images and ZIP/RAR/7z)",
    "Excluir permanentemente": "Delete permanently",
    "Excluir permanentemente (apaga tudo)": "Delete permanently (deletes everything)",
    "Mod não encontrado.": "Mod not found.",
    "Marvel Rivals está em execução. Feche o jogo para alterar mods ou ative 'Ignorar bloqueio de operações' nas configurações.": "Marvel Rivals is running. Close the game to change mods, or enable 'Bypass operation lock' in Settings.",
    "Visualizador 3D": "3D Viewer", "Componente Mesh": "Mesh component", "Texturas": "Textures",
    "Sem texturas": "No textures", "Centralizar": "Center", "Fechar visualizador": "Close viewer",
    "Preparando modelo e texturas…": "Preparing model and textures…",
    "Não foi possível preparar o modelo.": "Could not prepare the model.",
    "Nenhum Mesh renderizável foi encontrado.": "No renderable Mesh was found.",
    "Não encontrei a pasta Paks a partir do caminho de mods configurado.": "Could not find the Paks folder from the configured mods path.",
    "Arraste para girar · roda para aproximar · botão direito para mover · Esc para sair": "Drag to rotate · wheel to zoom · right button to pan · Esc to exit",
    "Fechar": "Close", "Carregando…": "Loading…", "Nenhum mod encontrado.": "No mods found.",
    "Todos": "All", "Variações": "Variations", "Complementos": "Add-ons", "Componentes": "Components",
    "Corrigir": "Correct", "Corrigir personagem e skin sem o scan desfazer a escolha": "Correct character and skin without a scan undoing the choice",
    "Nenhuma tag adicionada.": "No tags added.", "Diagnóstico": "Diagnostics", "Relações": "Relationships",
    "Ativo": "Enabled", "Desativado": "Disabled", "Prioridade": "Priority", "Conflitos": "Conflicts",
    "Biblioteca": "Library", "Conteúdo": "Content", "Avisos": "Warnings", "Antes": "Before", "Depois": "After",
    "Criar backup": "Create backup", "Confirmar": "Confirm", "Excluir": "Delete", "Restaurar": "Restore",
    "A cópia instalável em mods_storage continua existindo nas duas opções. Arquivos que já estão na biblioteca privada nunca são apagados. Ao importar vários pacotes soltos juntos, um único ZIP guarda todos eles sem misturar arquivos com nomes iguais.": "The installable copy in mods_storage remains available with either option. Files already in the private library are never deleted. When importing multiple loose packages together, one ZIP keeps all of them without mixing duplicate names.",
    "A cópia instalável em": "The installable copy in",
    "continua existindo nas duas opções. Arquivos que já estão na biblioteca privada nunca são apagados. Ao importar vários pacotes soltos juntos, um único ZIP guarda todos eles sem misturar arquivos com nomes iguais.": "remains available with either option. Files already in the private library are never deleted. When importing multiple loose packages together, one ZIP keeps all of them without mixing duplicate names.",
    "Salva cópias sequenciais em backups ou restaura catálogo, tags, capas cadastradas, componentes, perfis e configurações. Arquivos de mods e mídias não são copiados.": "Saves sequential copies in backups or restores the catalog, tags, registered covers, components, profiles, and settings. Mod and media files are not copied.",
    "Salva cópias sequenciais em": "Saves sequential copies in",
    "ou restaura catálogo, tags, capas cadastradas, componentes, perfis e configurações. Arquivos de mods e mídias não são copiados.": "or restores the catalog, tags, registered covers, components, profiles, and settings. Mod and media files are not copied.",
    "Inclui os arquivos dos mods, mídias e correções pessoais. Você escolhe o destino e revisa o espaço necessário antes de criar. A extração cria uma pasta nova, sem substituir esta biblioteca ou ativar mods.": "Includes mod files, media, and personal corrections. You choose the destination and review required space before creation. Extraction creates a new folder without replacing this library or enabling mods.",
    "Selecionar tema": "Select theme", "Selecionar cor de destaque": "Select accent color",
    "Clique em \"＋ Add Mod\" pra instalar o primeiro.": "Click \"＋ Add Mod\" to install the first one.",
    "+ Nova tag…": "+ New tag…", "Excluir tag": "Delete tag", "Excluir rótulo": "Delete label",
    "Mods genéricos não usam skin.": "Generic mods do not use skins.",
    "Nenhuma skin correspondente; você pode manter o texto digitado.": "No matching skin; you may keep the entered text.",
    "Arquivos ausentes": "Missing files", "Ainda não analisado": "Not analyzed yet",
    "Análise pendente": "Analysis pending", "Falha de leitura": "Read error",
    "Tipo não reconhecido": "Unrecognized type", "Analisado": "Analyzed",
    "Por que esta classificação?": "Why this classification?", "Identidade pelos assets:": "Identity from assets:",
    "Não identificada": "Not identified", "Reanalisar este componente": "Reanalyze this component",
    "Relações do componente": "Component relationships", "Grupo de alternativas": "Alternative group",
    "Depende destes componentes": "Depends on these components", "Nenhum outro componente.": "No other component.",
    "Salvar relações": "Save relationships", "Carregando detalhes…": "Loading details…",
    "Tentar novamente": "Try again", "Histórico do componente": "Component history",
    "Componentes removidos": "Removed components", "Nenhum componente removido.": "No removed components.",
    "Atualizar arquivos": "Update files", "Remover componente": "Remove component",
    "Gerenciar": "Manage", "Gerenciar componente": "Manage component",
    "Mais ações": "More actions", "Mais ações do componente": "More component actions",
    "Atualizar, restaurar versão ou remover": "Update, restore a version, or remove",
    "ATUALIZAÇÕES DO CRABVAULT": "CRABVAULT UPDATES",
    "Consulta a release estável mais recente no GitHub. O instalador só é executado depois de validar seu SHA-256 e preserva configurações, mods e mídias.": "Checks the latest stable release on GitHub. The installer only runs after its SHA-256 is validated and preserves settings, mods, and media.",
    "Versão instalada: 0.44.11.": "Installed version: 0.44.11.",
    "Verificar atualizações": "Check for updates",
    "Atualizar preserva nome, rótulo, ordem e estado. A versão anterior fica disponível no histórico.": "Updating preserves the name, label, order, and state. The previous version remains available in history.",
    "Selecione itens para editar o rótulo, ou arraste PAK/UCAS/UTOC/ZIP/RAR/7z aqui para adicionar variantes.": "Select items to edit the label, or drag PAK/UCAS/UTOC/ZIP/RAR/7z here to add variants.",
    "Remover mídia": "Remove media", "Escolher áudio": "Choose audio", "Renomear pacote": "Rename package",
    "Remover pacote": "Remove package", "Ouvir neste painel": "Listen in this panel",
    "Adicione primeiro um PAK de áudio.": "Add an audio PAK first.", "Ativar/desativar áudio": "Enable/disable audio",
    "Desvincular áudio": "Unlink audio", "Ativar/desativar esta cinematic": "Enable/disable this cinematic",
    "+ Complemento": "+ Add-on", "Botão direito para renomear": "Right-click to rename",
    "Ativar/desativar complemento": "Enable/disable add-on", "Remover complemento": "Remove add-on",
    "Nenhum complemento adicionado.": "No add-on added.", "Editar ordem": "Edit order", "Concluir ordem": "Finish ordering",
    "Adicionar variantes ou componentes a este mod": "Add variants or components to this mod",
    "Mostrar componentes": "Show components", "Esconder componentes": "Hide components",
    "Selecionar componente": "Select component", "Editar rótulo": "Edit label", "Editar nome": "Edit name",
    "Mostrar somente os arquivos deste componente": "Show only this component's files",
    "Conteúdo": "Contents", "Rótulo": "Label", "Nome": "Name", "Acompanhamento": "Companion",
    "Principal": "Main", "Ativar/desativar componente": "Enable/disable component",
    "Galeria": "Gallery", "+ Mídia": "+ Media", "Adicionar imagens ou vídeos à galeria": "Add images or videos to gallery",
    "Tamanho": "Size", "LINK DO MOD": "MOD LINK", "ARQUIVOS": "FILES", "TIPO E PERSONAGEM": "TYPE AND CHARACTER",
    "INFORMAÇÕES": "INFORMATION", "Ativado": "Enabled", "Instalar ReShade": "Install ReShade",
    "Instalar cinemáticas": "Install cinematics", "Adicionar áudio ao Background": "Add audio to Background",
    "Salve e recupere mods ativos e componentes.": "Save and restore enabled mods and components.",
    "Escolha o que manter ou desative um dos mods concorrentes.": "Choose what to keep or disable one of the conflicting mods.",
    "Escolha o que manter ou desative um dos mods concorrentes. O CrabVault não controla a ordem de carregamento do jogo.": "Choose what to keep or disable one of the conflicting mods. CrabVault does not control the game's load order.",
    "＋ Salvar estado atual": "＋ Save current state", "↶ Reverter última alteração": "↶ Revert last change",
    "↶ Nada para reverter": "↶ Nothing to revert", "Nenhuma alteração em massa disponível": "No bulk change available",
    "Focar a busca": "Focus search", "Atualizar a lista de mods": "Refresh the mod list",
    "Ativar/desativar todos os mods selecionados": "Enable/disable all selected mods",
    "Renomear o mod destacado": "Rename the focused mod", "Navegar pela lista de mods": "Navigate the mod list",
    "Setas ou WASD": "Arrow keys or WASD",
    "Nos Backgrounds, selecionar a prévia de cinematic anterior/próxima": "In Backgrounds, select the previous/next cinematic preview",
    "Abrir detalhes do mod destacado": "Open details for the focused mod",
    "Shift + clique": "Shift + click", "Selecionar o intervalo desde o último mod marcado": "Select the range from the last checked mod",
    "Fechar detalhes, janela ou menu aberto": "Close details, dialog, or open menu",
    "Mostrar esta ajuda": "Show this help", "⌨ Atalhos de teclado": "⌨ Keyboard Shortcuts",
    "Não foi possível instalar o mod:": "Could not install the mod:",
    "Se a operação foi interrompida, consulte Operações interrompidas nas configurações.": "If the operation was interrupted, check Interrupted operations in Settings.",
    "Escolha um personagem antes de continuar.": "Choose a character before continuing.",
    "Personagem inválido. Escolha um item da lista ou use Generic.": "Invalid character. Choose an item from the list or use Generic.",
    "Não foi possível ler os arquivos.": "Could not read the files.",
    "Não foi possível cancelar a seleção. Tente novamente.": "Could not cancel the selection. Try again.",
    "Não foi possível confirmar o resultado da instalação. Atualize a biblioteca e consulte Operações interrompidas nas configurações antes de importar novamente.": "Could not confirm the installation result. Refresh the library and check Interrupted operations in Settings before importing again.",
    "O mod foi instalado, mas alguns arquivos de origem foram preservados:": "The mod was installed, but some source files were preserved:",
    "O mod foi instalado, mas não foi possível atualizar a interface. Atualize a biblioteca.": "The mod was installed, but the interface could not be refreshed. Refresh the library.",
    "Não foi possível abrir a pasta do mod.": "Could not open the mod folder.",
    "Não foi possível abrir a prévia.": "Could not open the preview.",
    "Não foi possível abrir o conteúdo do componente.": "Could not open the component contents.",
    "Não foi possível abrir o jogo.": "Could not launch the game.",
    "Não foi possível adicionar as imagens.": "Could not add the images.",
    "Não foi possível adicionar os componentes.": "Could not add the components.",
    "Não foi possível alterar a capa.": "Could not change the cover.",
    "Não foi possível alterar a cinematic.": "Could not change the cinematic.",
    "Não foi possível alterar a ordem da galeria.": "Could not change the gallery order.",
    "Não foi possível alterar o áudio.": "Could not change the audio.",
    "Não foi possível alterar o complemento.": "Could not change the add-on.",
    "Não foi possível alterar o componente.": "Could not change the component.",
    "Não foi possível alterar o rótulo.": "Could not change the label.",
    "Não foi possível aplicar o perfil.": "Could not apply the profile.",
    "Não foi possível atualizar o perfil.": "Could not update the profile.",
    "Não foi possível atualizar os conflitos.": "Could not refresh conflicts.",
    "Não foi possível carregar a mídia.": "Could not load the media.",
    "Não foi possível carregar os detalhes.": "Could not load the details.",
    "Não foi possível concluir a análise. Reabra os detalhes para tentar novamente.": "Could not complete the analysis. Reopen Details to try again.",
    "Não foi possível corrigir a classificação.": "Could not correct the classification.",
    "Não foi possível criar a tag.": "Could not create the tag.",
    "Não foi possível criar o backup.": "Could not create the backup.",
    "Não foi possível criar o rótulo.": "Could not create the label.",
    "Não foi possível desativar o mod concorrente.": "Could not disable the conflicting mod.",
    "Não foi possível desvincular o áudio.": "Could not unlink the audio.",
    "Não foi possível excluir a tag.": "Could not delete the tag.",
    "Não foi possível excluir o perfil.": "Could not delete the profile.",
    "Não foi possível excluir o rótulo.": "Could not delete the label.",
    "Não foi possível limpar as entradas antigas.": "Could not clear the old entries.",
    "Não foi possível marcar o conflito.": "Could not mark the conflict.",
    "Não foi possível mover o mod.": "Could not move the mod.",
    "Não foi possível mover os componentes.": "Could not move the components.",
    "Não foi possível obter o diagnóstico.": "Could not get diagnostics.",
    "Não foi possível preparar a prévia de áudio.": "Could not prepare the audio preview.",
    "Não foi possível preparar o suporte 3D.": "Could not prepare 3D support.",
    "Não foi possível remover a cinematic.": "Could not remove the cinematic.",
    "Não foi possível remover a imagem.": "Could not remove the image.",
    "Não foi possível remover o complemento.": "Could not remove the add-on.",
    "Não foi possível remover o componente.": "Could not remove the component.",
    "Não foi possível remover o pacote.": "Could not remove the package.",
    "Não foi possível renomear o complemento.": "Could not rename the add-on.",
    "Não foi possível renomear o componente.": "Could not rename the component.",
    "Não foi possível renomear o mod.": "Could not rename the mod.",
    "Não foi possível renomear o pacote.": "Could not rename the package.",
    "Não foi possível restaurar o backup.": "Could not restore the backup.",
    "Não foi possível restaurar os Backgrounds.": "Could not restore Backgrounds.",
    "Não foi possível reverter a alteração.": "Could not revert the change.",
    "Não foi possível salvar a ordem.": "Could not save the order.",
    "Não foi possível salvar as relações.": "Could not save relationships.",
    "Não foi possível salvar o link.": "Could not save the link.",
    "Não foi possível salvar o perfil.": "Could not save the profile.",
    "Não foi possível verificar conflitos.": "Could not check conflicts.",
    "Não foi possível vincular o áudio.": "Could not link the audio.",
    "Nenhum mod novo encontrado. Os mods já detectados não são duplicados.": "No new mods found. Previously detected mods are not duplicated.",
    "Restaurar padrão": "Restore default",
    "Mostrar cinematics": "Show cinematics", "Esconder cinematics": "Hide cinematics",
    "Ver sugestões de relações": "View relationship suggestions",
    "Analisando componentes…": "Analyzing components…",
    "Análise concluída. Sem assets legíveis, a classificação anterior é mantida.": "Analysis complete. With no readable assets, the previous classification was kept.",
    "O visualizador 3D ainda não terminou de carregar.": "The 3D viewer has not finished loading yet.",
    "O Windows não forneceu os caminhos dos arquivos arrastados. Use o botão + para selecioná-los.": "Windows did not provide paths for the dropped files. Use the + button to select them.",
    "Alteração de áudio agendada. Ela será aplicada automaticamente quando o Marvel Rivals fechar.": "Audio change scheduled. It will be applied automatically after Marvel Rivals closes.",
    "A versão selecionada foi ativada e as outras versões desse mesmo vídeo foram desativadas.": "The selected version was enabled, and the other versions of the same video were disabled.",
    "O complemento foi ativado; versões concorrentes dos mesmos vídeos foram desativadas.": "The add-on was enabled; competing versions of the same videos were disabled.",
    "Limpar todo o histórico de alterações?": "Clear the entire activity history?",
    "Remover entradas do histórico anteriores a 30 dias?": "Remove history entries older than 30 days?",
    "Remover esta mídia da galeria?": "Remove this media from the gallery?",
    "Restaurar esta versão? A versão atual será guardada no histórico.": "Restore this version? The current version will be kept in history.",
    "Restaurar o MoviesBink original? Todos os mods de Background serão desativados.": "Restore the original MoviesBink? All Background mods will be disabled.",
    "Desvincular este áudio da cinematic? O banco continuará salvo na biblioteca.": "Unlink this audio from the cinematic? The bank will remain saved in the library.",
    "Adicione primeiro um PAK de áudio pelo botão + Áudio em Cinematics.": "First add an audio PAK using the + Audio button in Cinematics.",
    "O componente foi restaurado desativado porque seu estado antigo não é compatível com as relações atuais.": "The component was restored disabled because its previous state is incompatible with the current relationships.",
    "Essa ação entra em uma próxima etapa.": "This action is planned for a later stage.",
    "Nenhum personagem encontrado.": "No character found.",
    "Criar rótulo de componente": "Create component label",
    "Nome do componente:": "Component name:",
    "Nome do novo perfil:": "New profile name:",
    "Novo nome do pacote de áudio:": "New audio package name:",
    "Link do mod (deixe vazio para remover):": "Mod link (leave blank to remove):",
    "Prévia indisponível; clique para abrir a mídia.": "Preview unavailable; click to open the media.",
    "Prévia indisponível: o Bink Player não faz parte do Manager": "Preview unavailable: Bink Player is not part of the Manager",
    "Carregando perfis…": "Loading profiles…", "Nenhum perfil salvo ainda.": "No saved profile yet.",
    "Aplicar": "Apply", "Substituir pelo estado atual": "Replace with current state", "Excluir perfil": "Delete profile",
    "Histórico de atividade": "Activity history", "Importações, exclusões, prioridades, perfis, conflitos e reparos.": "Imports, deletions, priorities, profiles, conflicts, and repairs.",
    "Buscar no histórico…": "Search history…", "Todas as ações": "All actions", "Carregando histórico…": "Loading history…",
    "Tempos das últimas importações": "Latest import timings", "Nenhuma alteração registrada ainda.": "No changes recorded yet.",
    "Data não disponível": "Date unavailable", "Alteração no catálogo": "Catalog change",
    "Limpar anteriores a 30 dias": "Clear entries older than 30 days", "Limpar tudo": "Clear all",
    "Verificar conflitos": "Check conflicts", "Nenhum asset interno é sobrescrito por dois componentes ativos.": "No internal asset is overwritten by two enabled components.",
    "⚠ Conflitos de compatibilidade": "⚠ Compatibility conflicts", "Desativar este mod concorrente": "Disable this conflicting mod",
    "Desativar mod": "Disable mod", "Nenhum outro mod ativo identificado.": "No other enabled mod identified.",
    "O mod deste alerta continuará ativo.": "The mod from this alert will remain enabled.",
    "Procurando nas bibliotecas do Steam...": "Searching Steam libraries...", "Encontrado!": "Found!",
    "Não consegui achar automaticamente. Usa o Browse pra apontar manualmente.": "Automatic detection failed. Use Browse to select the folder manually.",
    "PASTA": "FOLDER", "Pasta": "Folder", "CAMINHO DO MOD": "MOD PATH",
    "ARQUIVOS": "FILES", "ARQUIVO": "FILE", "arquivo(s)": "file(s)", "arquivos": "files",
    "Importação de mod": "Mod import",
    "Revise a ação de recuperação. Os arquivos de origem das importações não serão apagados.": "Review the recovery action. Import source files will not be deleted.",
    "Descartar somente a preparação incompleta; os originais foram preservados.": "Discard only the incomplete preparation; the original files were preserved.",
    "Revisar recuperação": "Review recovery", "Confirmar recuperação": "Confirm recovery",
    "Consultando registros de recuperação…": "Checking recovery records…",
    "Nenhuma operação interrompida.": "No interrupted operation.",
    "Alterações posteriores incompatíveis serão bloqueadas.": "Incompatible later changes will be blocked.",
    "Recuperando arquivos e catálogo…": "Recovering files and catalog…",
    "Recuperação concluída.": "Recovery completed.",
    "Nenhum arquivo será alterado automaticamente.": "No file will be changed automatically.",
    "aguardam revisão": "await review", "operação(ões) interrompida(s)": "interrupted operation(s)",
    "Há um acompanhamento pendente:": "There is pending tracking:",
    "Retome para saber o resultado antes de repetir o pedido.": "Resume it to learn the result before repeating the request.",
    "Retomar acompanhamento": "Resume tracking",
    "Prioridade maior indica a preferência do Manager; não altera a ordem de carregamento do jogo.": "Higher priority indicates the Manager's preference; it does not change the game's load order.",
    "Removido em": "Removed on", "data não registrada": "date not recorded",
    "As cinematics de um complemento aparecem apenas quando ele está ativo. Clique com o botão direito em um complemento para renomeá-lo.": "An add-on's cinematics appear only while it is enabled. Right-click an add-on to rename it.",
    "ativo sobre este perfil": "enabled for this profile", "somente prévia": "preview only",
    "Arraste um componente ou o conjunto selecionado para mudar a ordem.": "Drag a component or the selected group to change the order.",
    "Selecione itens para editar o rótulo ou mover vários juntos.": "Select items to edit the label or move several together.",
    "Arraste um componente ou o grupo selecionado": "Drag a component or the selected group",
    "Áudio:": "Audio:", "aguardando o jogo fechar": "waiting for the game to close",
    "Não foi possível consultar as operações.": "Could not check the operations.",
    "Não foi possível recuperar esta operação.": "Could not recover this operation.",
    "Não foi possível acompanhar a operação. Consulte Operações interrompidas.": "Could not track the operation. Check Interrupted operations.",
    "Cancelando e preservando os arquivos originais…": "Cancelling and preserving the original files…",
    "Cancelando com segurança…": "Cancelling safely…", "Cancelar operação": "Cancel operation",
    "Concluindo, aguarde…": "Finishing, please wait…", "Reconectando ao pedido enviado…": "Reconnecting to the submitted request…",
    "A comunicação foi interrompida. Tentando recuperar o acompanhamento…": "Communication was interrupted. Trying to recover tracking…",
    "Nenhuma alteração será aplicada automaticamente.": "No change will be applied automatically.",
    "arquivos restaurados": "files restored", "mods verificados": "mods checked",
    "arquivos comparados por conteúdo": "files compared by content",
  }));

  const fragments = [...en.entries()].sort((left, right) => right[0].length - left[0].length);

  const patterns = [
    [/^Todos \((\d+)\)$/, "All ($1)"],
    [/^Variações \((\d+)\)$/, "Variations ($1)"],
    [/^Complementos \((\d+)\)$/, "Add-ons ($1)"],
    [/^Histórico \((\d+)\)$/, "History ($1)"],
    [/^Restaurar \((\d+)\)$/, "Restore ($1)"],
    [/^Excluído permanentemente: (.+)$/, "Permanently deleted: $1"],
    [/^Removido da biblioteca: (.+)$/, "Removed from library: $1"],
    [/^Ativados (\d+) mod\(s\)$/, "Enabled $1 mod(s)"],
    [/^Desativados (\d+) mod\(s\)$/, "Disabled $1 mod(s)"],
    [/^Componente ativado: (.+)$/, "Component enabled: $1"],
    [/^Componente desativado: (.+)$/, "Component disabled: $1"],
    [/^Ativado: (.+)$/, "Enabled: $1"],
    [/^Desativado: (.+)$/, "Disabled: $1"],
    [/^(\d+) mod\(s\) no snapshot$/, "$1 mod(s) in snapshot"],
    [/^Excluir a tag "(.+)" de todos os mods\?$/, "Delete the tag “$1” from every mod?"],
    [/^Aplicar o perfil “(.+)”\? Os switches e componentes atuais serão substituídos\.$/, "Apply profile “$1”? Current switches and components will be replaced."],
    [/^Atualizar o perfil “(.+)” com os mods e componentes atuais\?$/, "Update profile “$1” with the current mods and components?"],
    [/^Excluir o perfil “(.+)”\?$/, "Delete profile “$1”?"],
    [/^Perfil “(.+)” aplicado em (\d+) mod\(s\)\.$/, "Profile “$1” applied to $2 mod(s)."],
    [/^Remover a cinematic "(.+)" deste complemento\? Os outros vídeos do complemento serão mantidos\.$/, "Remove cinematic “$1” from this add-on? Its other videos will be kept."],
    [/^Remover o pacote de áudio "(.+)" da biblioteca\? Os vínculos deixarão de aparecer nas cinematics\.$/, "Remove audio package “$1” from the library? Its links will no longer appear on cinematics."],
    [/^Remover o complemento "(.+)"\? Ele será apagado da biblioteca, sem alterar o Background principal\.$/, "Remove add-on “$1”? It will be deleted from the library without changing the main Background."],
    [/^Não foi possível alterar "(.+)"\.$/, "Could not change “$1”."],
    [/^Prévia 3D preparada: (.+)$/, "3D preview prepared: $1"],
    [/^Não foi possível preparar o modelo 3D: (.+)$/, "Could not prepare the 3D model: $1"],
    [/^Adicionado (.+)$/, "Added $1"],
    [/^Atualizado (.+)$/, "Updated $1"],
    [/^(\d+) selecionado(?:s)?$/, "$1 selected"],
    [/^(\d+) mod\(s\)$/, "$1 mod(s)"],
    [/^(\d+) arquivo\(s\)$/, "$1 file(s)"],
    [/^(\d+) de (\d+)$/, "$1 of $2"],
    [/^(\d+) ativos$/, "$1 enabled"],
    [/^Ativando…$/, "Enabling…"], [/^Desativando…$/, "Disabling…"],
    [/^Salvando…$/, "Saving…"], [/^Carregando (.+)…$/, "Loading $1…"],
    [/^Não foi possível (.+)$/, "Could not $1"],
  ];
  const sourceText = new WeakMap();
  const sourceAttributes = new WeakMap();
  let language = "pt-BR";
  let translating = false;

  function translate(value) {
    if (language !== "en" || typeof value !== "string") return value;
    const leading = value.match(/^\s*/)?.[0] || "";
    const trailing = value.match(/\s*$/)?.[0] || "";
    const core = value.trim();
    if (!core) return value;
    if (en.has(core)) return leading + en.get(core) + trailing;
    let translated = core;
    for (const [pattern, replacement] of patterns) {
      if (!pattern.test(translated)) continue;
      translated = translated.replace(pattern, replacement);
      break;
    }
    for (const [portuguese, english] of fragments) {
      if (portuguese.length < 4 || !translated.includes(portuguese)) continue;
      translated = translated.replaceAll(portuguese, english);
    }
    return translated === core ? value : leading + translated + trailing;
  }

  function translateText(node) {
    if (!sourceText.has(node)) sourceText.set(node, node.nodeValue);
    const original = sourceText.get(node);
    const wanted = language === "en" ? translate(original) : original;
    if (node.nodeValue !== wanted) node.nodeValue = wanted;
  }

  function translateElement(element) {
    if (!(element instanceof Element)) return;
    let originals = sourceAttributes.get(element);
    if (!originals) { originals = {}; sourceAttributes.set(element, originals); }
    for (const attribute of ["title", "placeholder", "aria-label", "data-tooltip"]) {
      if (!element.hasAttribute(attribute)) continue;
      if (!(attribute in originals)) originals[attribute] = element.getAttribute(attribute);
      const wanted = language === "en" ? translate(originals[attribute]) : originals[attribute];
      if (element.getAttribute(attribute) !== wanted) element.setAttribute(attribute, wanted);
    }
  }

  function apply(root = document.body) {
    if (!root || translating) return;
    translating = true;
    try {
      if (root.nodeType === Node.TEXT_NODE) translateText(root);
      else {
        translateElement(root);
        const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) walker.currentNode.nodeType === Node.TEXT_NODE
          ? translateText(walker.currentNode) : translateElement(walker.currentNode);
      }
      document.documentElement.lang = language === "en" ? "en" : "pt-BR";
    } finally { translating = false; }
  }

  window.uiText = value => translate(String(value ?? ""));
  window.setUiLanguage = value => { language = value === "en" ? "en" : "pt-BR"; apply(); };
  window.getUiLanguage = () => language;

  const originalAlert = window.alert.bind(window);
  const originalConfirm = window.confirm.bind(window);
  window.alert = message => originalAlert(translate(String(message ?? "")));
  window.confirm = message => originalConfirm(translate(String(message ?? "")));

  new MutationObserver(records => {
    if (translating) return;
    for (const record of records) {
      if (record.type === "characterData") {
        const previous = sourceText.get(record.target);
        const rendered = previous == null ? null : (language === "en" ? translate(previous) : previous);
        if (previous == null || record.target.nodeValue !== rendered) sourceText.set(record.target, record.target.nodeValue);
        apply(record.target);
      } else if (record.type === "attributes") {
        const attribute = record.attributeName;
        let originals = sourceAttributes.get(record.target);
        if (!originals) { originals = {}; sourceAttributes.set(record.target, originals); }
        const previous = originals[attribute];
        const rendered = previous == null ? null : (language === "en" ? translate(previous) : previous);
        if (previous == null || record.target.getAttribute(attribute) !== rendered) originals[attribute] = record.target.getAttribute(attribute);
        apply(record.target);
      } else for (const node of record.addedNodes) apply(node);
    }
  }).observe(document.documentElement, {subtree:true, childList:true, characterData:true, attributes:true,
    attributeFilter:["title", "placeholder", "aria-label", "data-tooltip"]});
})();
