// Ferramentas sob demanda: não varrem nem reclassificam a biblioteca ao abrir.
const classificationStatusNames = {
  missing: "Arquivos ausentes", pending: "Ainda não analisado",
  read_error: "Falha de leitura", unrecognized: "Tipo não reconhecido", analyzed: "Analisado",
};

function maintenanceError(overlay, error) {
  const target = overlay.querySelector(".dialog-error");
  if (target) target.textContent = error?.message || String(error);
}

async function refreshMaintainedMods(ids) {
  for (const id of new Set(ids)) await refreshModInState(id);
  renderLocalChange();
  if (ids.includes(state.detailsModId)) await showModDetailsPage(state.detailsModId, { onlyIfOpen: true });
}

async function showPendingClassifications() {
  const overlay = openComponentDialog("Classificações pendentes", '<p role="status">Consultando os registros da biblioteca…</p>');
  try {
    const report = await api().list_pending_classifications();
    if (!report?.ok) throw new Error(report?.error || "Não foi possível consultar as classificações.");
    if (!overlay.isConnected) return;
    const rows = report.components || [];
    const body = document.createElement("div");
    body.className = "pending-classification-body";
    body.innerHTML = `<p>Reanalise somente o que você selecionar. Personagem, skin, nomes e switches serão preservados.</p>
      <div class="maintenance-filters"><input type="search" class="pending-search" aria-label="Buscar classificação" placeholder="Buscar mod ou componente"><select class="pending-status" aria-label="Filtrar estado"><option value="">Todos os estados</option>${[...new Set(rows.map(row => row.status))].map(status => `<option value="${escapeHtml(status)}">${escapeHtml(classificationStatusNames[status] || status)}</option>`).join("")}</select></div>
      <label><input type="checkbox" class="pending-select-all"> Selecionar os resultados visíveis</label>
      <div class="maintenance-list">${rows.map((row, index) => `<label class="pending-row" data-index="${index}"><input type="checkbox" class="pending-select" value="${index}"><span><b>${escapeHtml(row.mod_name)} · ${escapeHtml(row.component_name)}</b><small>${escapeHtml(classificationStatusNames[row.status] || row.status)} · ${escapeHtml(row.types?.join(" + ") || "Unknown")}</small><small>${escapeHtml(row.message || "")}</small></span></label>`).join("") || '<p class="maintenance-empty">Nenhuma classificação pendente.</p>'}</div>
      <p class="pending-summary" role="status"></p><div class="maintenance-actions"><button class="btn primary pending-run" ${rows.length ? "" : "disabled"}>Reanalisar selecionados</button><button class="btn pending-stop" hidden>Parar após o atual</button></div>`;
    overlay.querySelector('[role="status"]').replaceWith(body);
    const search = body.querySelector(".pending-search"), status = body.querySelector(".pending-status");
    const selectAll = body.querySelector(".pending-select-all"), summary = body.querySelector(".pending-summary");
    const update = () => {
      let visible = 0;
      body.querySelectorAll(".pending-row").forEach(element => {
        const row = rows[Number(element.dataset.index)];
        element.hidden = (!!status.value && row.status !== status.value) || !`${row.mod_name} ${row.component_name}`.toLocaleLowerCase().includes(search.value.toLocaleLowerCase());
        if (!element.hidden) visible++;
      });
      const selected = body.querySelectorAll(".pending-select:checked").length;
      summary.textContent = `${visible} resultado(s) · ${selected} selecionado(s)`;
      body.querySelector(".pending-run").disabled = !selected;
      const visibleChecks = [...body.querySelectorAll(".pending-row:not([hidden]) .pending-select")];
      selectAll.checked = visibleChecks.length > 0 && visibleChecks.every(input => input.checked);
      selectAll.indeterminate = !selectAll.checked && visibleChecks.some(input => input.checked);
    };
    search.oninput = status.onchange = update;
    body.querySelectorAll(".pending-select").forEach(input => { input.onchange = update; });
    selectAll.onchange = () => { body.querySelectorAll(".pending-row:not([hidden]) .pending-select").forEach(input => { input.checked = selectAll.checked; }); update(); };
    update();
    body.querySelector(".pending-run").onclick = async () => {
      const selected = [...body.querySelectorAll(".pending-select:checked")].map(input => rows[Number(input.value)]);
      const changed = [], failures = [];
      let stop = false, finished = 0;
      body.querySelectorAll("input, select, .pending-run").forEach(control => { control.disabled = true; });
      const stopButton = body.querySelector(".pending-stop");
      stopButton.hidden = false;
      stopButton.onclick = () => { stop = true; stopButton.disabled = true; stopButton.textContent = "Parando após a análise atual…"; };
      for (const row of selected) {
        if (stop || !overlay.isConnected) break;
        summary.textContent = `Analisando ${finished + 1}/${selected.length}: ${row.component_name}`;
        try {
          const result = await api().reanalyze_selected_components([{ mod_id: row.mod_id, component_id: row.component_id }]);
          const failure = result?.results?.find(item => !item.ok);
          if (!result?.ok || failure) throw new Error(result?.error || failure?.error || "Falha na leitura.");
          changed.push(row.mod_id);
        } catch (error) { failures.push(`${row.mod_name} · ${row.component_name}: ${error.message}`); }
        finished++;
      }
      await refreshMaintainedMods(changed);
      if (!overlay.isConnected) return;
      summary.textContent = `${finished}/${selected.length} componente(s) processados${stop ? " · interrompido por você" : ""}.`;
      stopButton.hidden = true;
      body.querySelector(".pending-run").hidden = true;
      if (failures.length) maintenanceError(overlay, failures.join("\n"));
      const reload = document.createElement("button");
      reload.className = "btn"; reload.textContent = "Atualizar pendências";
      reload.onclick = () => void showPendingClassifications();
      body.querySelector(".maintenance-actions").appendChild(reload);
    };
  } catch (error) { maintenanceError(overlay, error); }
}

function simplifyComponentActions(mod, components, ordering) {
  if (ordering) return;
  const container = document.querySelector("#mod-detail-content .detail-components");
  if (!container) return;
  const rows = [...container.querySelectorAll(".detail-component")];
  const kind = component => component.exclusive_group || (component.types || [component.type]).includes("Mesh") ? "variant" : (component.types || [component.type]).some(type => ["Texture", "Physics", "Audio", "UI"].includes(type)) ? "extra" : "other";
  rows.forEach(row => {
    const component = components.find(item => item.id === row.dataset.componentId);
    if (!component) return;
    row.dataset.componentKind = kind(component);
    const actions = row.querySelector(".component-actions");
    const secondary = [...actions.querySelectorAll(".component-label-edit, .component-rename, .component-extra-action")];
    if (!secondary.length) return;
    const more = document.createElement("details"); more.className = "component-more";
    more.innerHTML = '<summary aria-label="Mais ações do componente" title="Mais ações">⋯</summary><div class="component-more-menu"></div>';
    secondary.forEach(button => {
      if (button.classList.contains("component-manage")) {
        button.textContent = "Gerenciar";
        button.title = "Gerenciar componente";
      }
      more.querySelector("div").appendChild(button);
    });
    more.addEventListener("toggle", () => { if (more.open) container.querySelectorAll(".component-more[open]").forEach(other => { if (other !== more) other.open = false; }); });
    more.onkeydown = event => { if (event.key === "Escape") { event.stopPropagation(); more.open = false; more.querySelector("summary").focus(); } };
    more.querySelector("div").addEventListener("click", event => { if (event.target.closest("button")) more.open = false; });
    actions.insertBefore(more, actions.querySelector(".component-switch"));
  });
  const variants = rows.filter(row => row.dataset.componentKind === "variant").length;
  const extras = rows.filter(row => row.dataset.componentKind === "extra").length;
  if (!variants || !extras) return;
  const filters = document.createElement("div"); filters.className = "component-kind-filters";
  const label = value => globalThis.window?.uiText?.(value) || value;
  filters.innerHTML = `<button data-kind="" aria-pressed="false">${label("Todos")} (${rows.length})</button><button data-kind="variant" aria-pressed="false">${label("Variações")} (${variants})</button><button data-kind="extra" aria-pressed="false">${label("Complementos")} (${extras})</button>`;
  const selectKind = kind => {
    const activeKind = ["variant", "extra"].includes(kind) ? kind : "";
    state.componentKindFilters.set(mod.id, activeKind);
    rows.forEach(row => { row.hidden = !!activeKind && row.dataset.componentKind !== activeKind; });
    filters.querySelectorAll("button").forEach(item => {
      const selected = item.dataset.kind === activeKind;
      item.classList.toggle("selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
  };
  filters.onclick = event => {
    const button = event.target.closest("button"); if (!button) return;
    selectKind(button.dataset.kind);
  };
  container.before(filters);
  selectKind(state.componentKindFilters.get(mod.id));
}

document.getElementById("setting-pending-classifications").onclick = () => void showPendingClassifications();

let lastLibraryHealth = null;
const maintenanceNote = value => typeof value === "string" ? value : value?.reason || value?.message || value?.name || JSON.stringify(value);
const repairVerificationNames = { sha256: "Conteúdo conferido pelo hash SHA-256", size: "Tamanho conferido; não há hash do original", copy_only: "Cópia disponível; não há hash ou tamanho do original" };
const healthFileNote = item => {
  const location = { library: "Biblioteca privada", game: "Pasta do jogo", copies: "Cópias privada e ativa" }[item.location] || "";
  return `<p><code>${escapeHtml(item.name || "Arquivo")}</code><br>${escapeHtml([location, item.message || "Conteúdo diferente do registrado na importação."].filter(Boolean).join(" · "))}</p>`;
};

function renderLibraryHealth(report) {
  const target = document.getElementById("library-health-result");
  if (!report?.ok) { target.innerHTML = `<div class="library-health-warning">${escapeHtml(report?.error || "Não foi possível verificar a biblioteca.")}</div>`; return; }
  lastLibraryHealth = report;
  const issues = report.issues || [], orphans = report.orphans || [];
  const critical = issues.filter(issue => issue.missing_backup?.length || issue.missing_active?.length || issue.missing_media?.length || issue.hash_mismatches?.length || issue.unreadable?.length || issue.external_disabled);
  const summary = `${report.checked || 0} mod(s) verificados · ${report.hashed_files || 0} arquivo(s) comparados por conteúdo.`;
  target.innerHTML = `<div class="${critical.length ? "library-health-warning" : "library-health-ok"}">${critical.length ? `${critical.length} mod(s) com pendências. ` : "Nenhum problema confirmado. "}${escapeHtml(summary)}</div>
    ${report.mods_path_configured ? "" : '<p>O caminho do jogo não está configurado; os arquivos ativos não foram verificados.</p>'}
    ${issues.length ? `<ul>${issues.map((issue, index) => {
      const notes = [];
      for (const [field, label] of [["missing_backup","arquivo privado ausente"],["missing_active","arquivo ativo ausente"],["missing_media","mídia ausente"],["hash_mismatches","conteúdo divergente"],["unreadable","arquivo sem acesso"],["unverifiable","arquivo sem hash de referência"]]) if (issue[field]?.length) notes.push(`${issue[field].length} ${label}(s)`);
      if (issue.external_disabled) notes.push("mod externo desativado sem cópia privada");
      const repair = issue.missing_backup?.length || issue.missing_active?.length;
      return `<li><strong>${escapeHtml(issue.name || "Mod")}</strong><span>${escapeHtml(notes.join(" · "))}</span><div class="library-health-actions">${repair ? `<button class="btn library-health-repair" data-health-repair="${index}">Revisar reparo</button>` : ""}${issue.missing_media?.length ? `<button class="btn library-health-ignore" data-health-ignore="${index}">Ignorar mídia ausente</button>` : ""}</div>${issue.hash_mismatches?.length ? `<details><summary>Ver divergências</summary>${issue.hash_mismatches.map(healthFileNote).join("")}</details>` : ""}${issue.unreadable?.length ? `<details><summary>Ver arquivos sem acesso</summary>${issue.unreadable.map(healthFileNote).join("")}</details>` : ""}</li>`;
    }).join("")}</ul>` : ""}
    ${issues.some(issue => issue.unverifiable?.length) ? '<p>Arquivos antigos sem hash de referência não podem ser comparados ao original. Isso, por si só, não indica corrupção.</p>' : ""}
    ${orphans.length ? `<details class="health-orphans"><summary>${orphans.length} pasta(s) sem vínculo com o catálogo</summary><p>Podem ser compactados e mídias preservados pela remoção de mods ou importações incompletas. Nada será apagado.</p>${orphans.map(item => `<p><code>${escapeHtml(item.relative_path || item.path || "")}</code> · ${escapeHtml(item.kind || "conteúdo sem registro")}</p>`).join("")}</details>` : ""}
    ${(report.warnings || []).map(note => `<p>${escapeHtml(maintenanceNote(note))}</p>`).join("")}`;
}

async function runLibraryHealth() {
  const button = document.getElementById("setting-check-library");
  button.disabled = true; button.textContent = "Verificando arquivos…";
  try {
    const requestId = newOperationRequest("health");
    const result = await runImportOperation(() => api().start_library_health(document.getElementById("setting-verify-hashes").checked, requestId),
      "Verificando integridade", { requestId, context: { kind: "health" } });
    if (!result?.cancelled) renderLibraryHealth(result);
  }
  catch (error) { renderLibraryHealth({ ok: false, error: error.message }); }
  finally { button.disabled = false; button.textContent = "Verificar integridade"; }
}

async function refreshLibraryHealthMod(modId) {
  const report = await api().inspect_library_health(document.getElementById("setting-verify-hashes").checked, [modId]);
  if (!report?.ok || !lastLibraryHealth) { renderLibraryHealth(report); return; }
  renderLibraryHealth({ ...lastLibraryHealth, issues: [...lastLibraryHealth.issues.filter(issue => (issue.mod_id || issue.id) !== modId), ...(report.issues || [])] });
}

async function showLibraryRepair(modId) {
  const overlay = openComponentDialog("Revisar reparo", '<p role="status">Verificando quais cópias podem ser restauradas com segurança…</p>');
  try {
    const plan = await api().preview_library_repair(modId);
    if (!plan?.ok) throw new Error(plan?.error || "Não foi possível preparar o reparo.");
    if (!overlay.isConnected) return;
    const body = document.createElement("div"), actions = plan.actions || [];
    body.innerHTML = `<p>Somente arquivos ausentes serão copiados. Nenhum arquivo existente será sobrescrito.</p><div class="maintenance-list">${actions.map((action, index) => `<label class="pending-row"><input class="repair-action" type="checkbox" value="${index}" checked><span><b>${escapeHtml(action.name)}</b><small>${escapeHtml(action.source_label)} → ${escapeHtml(action.destination_label)}</small><small>${escapeHtml(repairVerificationNames[action.verification] || maintenanceNote(action.verification || ""))}</small></span></label>`).join("") || '<p class="maintenance-empty">Nenhuma cópia disponível para reparo automático.</p>'}</div>${[...(plan.blocked || []), ...(plan.warnings || [])].map(note => `<p>${escapeHtml(maintenanceNote(note))}</p>`).join("")}<button class="btn primary apply-repair" ${actions.length ? "" : "disabled"}>Restaurar arquivos selecionados</button><p class="repair-result" role="status"></p>`;
    overlay.querySelector('[role="status"]').replaceWith(body);
    const apply = body.querySelector(".apply-repair");
    body.querySelectorAll(".repair-action").forEach(input => { input.onchange = () => { apply.disabled = !body.querySelector(".repair-action:checked"); }; });
    apply.onclick = async () => {
      apply.disabled = true;
      body.querySelectorAll("input").forEach(input => { input.disabled = true; });
      body.querySelector(".repair-result").textContent = "Revalidando e restaurando arquivos…";
      try {
        const ids = [...body.querySelectorAll(".repair-action:checked")].map(input => actions[Number(input.value)].id);
        const result = await api().apply_library_repair(plan.token, ids);
        if (!result?.ok) throw new Error(result?.error || "O reparo não foi concluído. Abra uma nova revisão.");
        body.querySelector(".repair-result").textContent = `${(result.repaired_backup?.length || 0) + (result.repaired_active?.length || 0)} arquivo(s) restaurados.`;
        for (const warning of [...(result.warnings || []), ...(result.unavailable || [])]) {
          const note = document.createElement("p"); note.textContent = maintenanceNote(warning); body.appendChild(note);
        }
        await refreshLibraryHealthMod(modId);
        await refreshMaintainedMods([modId]);
      } catch (error) { maintenanceError(overlay, error); }
    };
  } catch (error) { maintenanceError(overlay, error); }
}

document.getElementById("setting-check-library").onclick = () => void runLibraryHealth();

const operationStorageKey = "marvel-manager.pending-operation";
const preparedImportStorageKey = "marvel-manager.prepared-import";
function pendingOperation() {
  if (state.pendingOperation) return state.pendingOperation;
  try {
    return JSON.parse(window.sessionStorage.getItem(operationStorageKey))
      || (!state.installToken && JSON.parse(window.sessionStorage.getItem(preparedImportStorageKey))) || null;
  } catch (_) { return null; }
}
function rememberPreparedImport(value) {
  try { window.sessionStorage.setItem(preparedImportStorageKey, JSON.stringify(value)); } catch (_) { /* Seleção disponível nesta janela. */ }
}
function clearPreparedImport() {
  try { window.sessionStorage.removeItem(preparedImportStorageKey); } catch (_) { /* Sem armazenamento de sessão. */ }
}
function rememberOperation(value) {
  state.pendingOperation = value;
  if (value?.context?.kind === "import_commit") clearPreparedImport();
  try {
    if (value) window.sessionStorage.setItem(operationStorageKey, JSON.stringify(value));
    else window.sessionStorage.removeItem(operationStorageKey);
  } catch (_) { /* Acompanhamento continua disponível nesta janela. */ }
}
function newOperationRequest(kind) { return `${kind}:${window.crypto.randomUUID()}`; }

async function runImportOperation(start, title, options = {}) {
  if (state.importBusy) return { ok: false, error: "Aguarde a operação atual." };
  const previous = pendingOperation();
  if (previous && previous.requestId !== options.requestId) return { ok: false, error: "Retome o acompanhamento da operação anterior antes de iniciar outra." };
  state.importBusy = true;
  const controls = ["btn-add-mod", "btn-add-reshade", "btn-add-background", "add-mod-close", "add-mod-cancel"].map(id => document.getElementById(id));
  const previousDisabled = controls.map(button => button.disabled);
  controls.forEach(button => { button.disabled = true; });
  const overlay = openComponentDialog(title, '<p class="operation-message" role="status">Aguardando seleção dos arquivos…</p><progress class="operation-progress" max="100" aria-label="Progresso da operação"></progress><p class="operation-count"></p><button class="btn operation-cancel" disabled>Cancelar operação</button>');
  overlay.dataset.busy = "true";
  overlay.querySelector(".dialog-close").hidden = true;
  overlay.querySelector(".diagnostic-dialog").classList.add("operation-dialog");
  overlay.querySelector(".diagnostic-dialog").focus();
  let jobId = null, cancellationRequested = false, settled = false, communicationFailures = 0;
  if (options.requestId) rememberOperation({ requestId: options.requestId, context: options.context || {}, title });
  const message = overlay.querySelector(".operation-message"), progress = overlay.querySelector("progress"), count = overlay.querySelector(".operation-count"), cancel = overlay.querySelector(".operation-cancel");
  cancel.onclick = async () => {
    if (!jobId || cancellationRequested) return;
    cancellationRequested = true; cancel.disabled = true; cancel.textContent = "Cancelando com segurança…";
    try {
      const result = await api().cancel_operation(jobId);
      if (!result?.ok) { cancellationRequested = false; maintenanceError(overlay, result?.error || "Não foi possível cancelar."); }
    } catch (error) { cancellationRequested = false; maintenanceError(overlay, error); }
  };
  try {
    message.textContent = title + "…";
    let started;
    try { started = await start(); }
    catch (error) {
      if (!options.requestId) throw error;
      message.textContent = "Reconectando ao pedido enviado…";
      started = await api().find_operation(options.requestId);
      if (!started?.found) throw new Error("Não foi possível recuperar o acompanhamento agora. Use Retomar acompanhamento antes de iniciar outra operação.");
    }
    if (!started?.job_id) { settled = true; return started; }
    jobId = started.job_id;
    while (true) {
      let status;
      try { status = await api().get_operation_status(jobId); }
      catch (error) {
        message.textContent = "A comunicação foi interrompida. Tentando recuperar o acompanhamento…";
        cancel.disabled = true;
        if (++communicationFailures >= 5) throw new Error("A comunicação continua indisponível. A operação pode estar em andamento; use Retomar acompanhamento quando a conexão voltar.");
        await new Promise(resolve => setTimeout(resolve, 1000));
        continue;
      }
      communicationFailures = 0;
      if (!status?.ok) throw new Error(status?.error || "Não foi possível acompanhar a operação. Consulte Operações interrompidas.");
      message.textContent = cancellationRequested ? "Cancelando e preservando os arquivos originais…" : status.message || title;
      cancel.disabled = !status.can_cancel || cancellationRequested;
      cancel.textContent = cancellationRequested ? "Cancelando com segurança…" : status.can_cancel ? "Cancelar operação" : "Concluindo, aguarde…";
      const total = Number(status.total) || 0, current = Number(status.current) || 0;
      if (total > 0) {
        progress.value = Math.min(100, Math.round(current / total * 100));
        count.textContent = status.unit === "bytes" ? `${formatModSize(current / 1048576)} de ${formatModSize(total / 1048576)}` : `${current} de ${total}`;
      } else { progress.removeAttribute("value"); count.textContent = ""; }
      if (["completed", "failed", "cancelled"].includes(status.state)) {
        settled = true;
        return status.result || { ok: false, cancelled: status.state === "cancelled", error: status.error };
      }
      await new Promise(resolve => setTimeout(resolve, 350));
    }
  } finally {
    if (settled && options.requestId) rememberOperation(null);
    overlay.remove();
    state.importBusy = false;
    controls.forEach((button, index) => { button.disabled = previousDisabled[index]; });
    void refreshOperationNotice();
  }
}

async function refreshOperationNotice() {
  try {
    const result = await api().get_operation_recoveries();
    if (!result?.ok) return;
    const notice = document.getElementById("operation-recovery-notice"), count = result.operations?.length || 0;
    const pending = pendingOperation();
    notice.hidden = !count && !pending;
    notice.querySelector("span").textContent = pending
      ? `Há um acompanhamento pendente: ${pending.title}. Retome para saber o resultado antes de repetir o pedido.`
      : `${count} operação(ões) interrompida(s) aguardam revisão. Nenhum arquivo será alterado automaticamente.`;
    notice.querySelector("button").textContent = pending ? "Retomar acompanhamento" : "Revisar";
  } catch (_) { /* Não impede abrir a biblioteca se o diagnóstico estiver indisponível. */ }
}

async function showInterruptedOperations() {
  const overlay = openComponentDialog("Operações interrompidas", '<p role="status">Consultando registros de recuperação…</p>');
  try {
    const result = await api().get_operation_recoveries();
    if (!result?.ok) throw new Error(result?.error || "Não foi possível consultar as operações.");
    if (!overlay.isConnected) return;
    const body = document.createElement("div"), operations = result.operations || [];
    body.innerHTML = `<p>Revise a ação de recuperação. Os arquivos de origem das importações não serão apagados.</p>${operations.map((operation, index) => `<article class="maintenance-operation"><b>${escapeHtml(operation.title)}</b><small>${escapeHtml(operation.created_at || "")}</small><p>${escapeHtml(operation.message)}</p>${operation.error ? `<p class="dialog-error">${escapeHtml(operation.error)}</p>` : ""}<button class="btn review-recovery" data-index="${index}" ${operation.can_restore ? "" : "disabled"}>Revisar recuperação</button></article>`).join("") || '<p class="maintenance-empty">Nenhuma operação interrompida.</p>'}`;
    overlay.querySelector('[role="status"]').replaceWith(body);
    body.querySelectorAll(".review-recovery").forEach(button => { button.onclick = () => {
      const operation = operations[Number(button.dataset.index)], panel = button.closest("article");
      if (panel.querySelector(".confirm-recovery")) return;
      const confirmation = document.createElement("div"); confirmation.className = "confirm-recovery";
      confirmation.innerHTML = `<p>${escapeHtml(operation.message)} Alterações posteriores incompatíveis serão bloqueadas.</p><button class="btn primary apply-recovery">Confirmar recuperação</button><p class="recovery-result" role="status"></p>`;
      panel.appendChild(confirmation); button.hidden = true;
      confirmation.querySelector("button").onclick = async event => {
        event.target.disabled = true; overlay.dataset.busy = "true";
        confirmation.querySelector(".recovery-result").textContent = "Recuperando arquivos e catálogo…";
        try {
          const recovered = await api().recover_interrupted_operation(operation.id);
          if (!recovered?.ok) throw new Error(recovered?.error || "Não foi possível recuperar esta operação.");
          confirmation.querySelector(".recovery-result").textContent = "Recuperação concluída.";
          await reloadAll(); await refreshOperationNotice();
        } catch (error) { maintenanceError(overlay, error); event.target.disabled = false; }
        finally { overlay.dataset.busy = "false"; }
      };
    }; });
  } catch (error) { maintenanceError(overlay, error); }
}

document.getElementById("setting-recover-operations").onclick = () => void showInterruptedOperations();
document.getElementById("review-interrupted-operations").onclick = () => void (pendingOperation() ? resumeLastOperation() : showInterruptedOperations());

async function resumeLastOperation() {
  if (state.importBusy) return;
  const pending = pendingOperation();
  if (!pending) return;
  try {
    const found = await api().find_operation(pending.requestId);
    if (!found?.ok) throw new Error(found?.error || "Não foi possível consultar a operação.");
    if (!found.found) {
      rememberOperation(null);
      clearPreparedImport();
      await refreshOperationNotice();
      alert("Esta operação não está mais nesta sessão. Confira a biblioteca e revise as operações interrompidas; nenhum pedido foi reenviado.");
      await showInterruptedOperations();
      return;
    }
    const result = await runImportOperation(async () => found, pending.title, pending);
    if (result?.cancelled) return;
    if (!result?.ok) throw new Error(result?.error || "A operação não foi concluída.");
    const context = pending.context;
    if (context.kind === "import_prepare") await openInstallSelection(result, context.parent_background_id, pending);
    else if (context.kind === "import_commit") {
      await reloadAll();
      alert("Importação concluída. " + (result.source_cleanup?.errors?.length ? "Alguns arquivos de origem foram preservados." : ""));
      if (context.parent_background_id) await showModDetailsPage(context.parent_background_id);
    } else if (context.kind === "health") {
      document.getElementById("btn-settings").click(); renderLibraryHealth(result);
    } else if (context.kind === "conflicts") {
      // O job reencontrado pode ter terminado antes de um switch ser alterado.
      // Consulta o estado atual em vez de reapresentar seu relatório antigo.
      state.conflictShowResultsPending = true;
      await refreshConflictIndicators();
    } else if (context.kind === "native3d_support") {
      document.getElementById("btn-settings").click();
    } else if (context.kind === "component_append") {
      await finishComponentImport(result, context.mod_id, context.target_component_id || null);
    } else if (context.kind === "backup_preview") showFullBackupPlan(result);
    else if (context.kind === "restore_preview") showFullRestorePlan(result);
    else if (context.kind === "backup_create" || context.kind === "backup_restore") showFullBackupResult(result, context.kind === "backup_restore");
  } catch (error) { alert(error.message); }
}

function clearPersonalImportChoice(message = "") {
  const hadChoice = !!state.personalCorrectionChoice;
  state.personalCorrectionChoice = null;
  state.personalCorrectionIdentityBefore = null;
  const select = document.getElementById("install-correction-choice");
  if (select) select.value = "";
  if (hadChoice && message) document.getElementById("install-correction-note").textContent = message;
}

async function setPersonalImportIdentity(identity) {
  await selectCharacter(identity.character, { preserveCorrection: true });
  state.pickedSkin = identity.skin || "";
  inputSkinNew.value = state.pickedSkin;
  skinChipsWrap.querySelectorAll(".skin-chip").forEach(chip => chip.classList.toggle("selected", chip.textContent === state.pickedSkin));
  updateSuggestedInstallFolder();
}

function renderPersonalImportChoices(result) {
  clearPersonalImportChoice();
  const box = document.getElementById("install-personal-corrections"), select = document.getElementById("install-correction-choice");
  state.personalCorrectionOffers = result?.offers || [];
  box.hidden = !state.personalCorrectionOffers.length;
  select.innerHTML = '<option value="">Não reutilizar correções</option>' + state.personalCorrectionOffers.map(offer =>
    `<option value="${escapeHtml(offer.id)}">${escapeHtml(offer.source_name)} · ${offer.matched_components}/${offer.total_components} componente(s)</option>`).join("");
  document.getElementById("install-correction-note").textContent = "Encontramos conteúdo idêntico por hash. Escolha uma opção para revisar antes de reutilizar.";
  select.onchange = async () => {
    const selected = select.value;
    select.value = state.personalCorrectionChoice || "";
    if (!selected) {
      const identity = state.personalCorrectionIdentityBefore;
      clearPersonalImportChoice();
      select.disabled = true;
      try {
        if (identity) await setPersonalImportIdentity(identity);
        document.getElementById("install-correction-note").textContent = "Nenhuma correção salva será reutilizada.";
      } catch (error) { alert("Não foi possível atualizar a seleção: " + error.message); }
      finally { select.disabled = false; }
      return;
    }
    const offer = state.personalCorrectionOffers.find(item => item.id === selected);
    if (offer) showPersonalImportReview(offer);
  };
}

function showPersonalImportReview(offer) {
  const fieldNames = { name: "Nome", description: "Rótulo", exclusive_group: "Grupo de alternativas", requires: "Dependências" };
  const fieldValue = (field, value) => field === "requires"
    ? (value || []).map(id => offer.component_names?.[id] || "Componente da seleção").join(", ") || "Nenhuma"
    : String(value || "—");
  const identityText = identity => `${identity.character} / ${identity.skin || "Sem skin"}`;
  const identity = offer.identity ? `<p><b>Identidade:</b> ${escapeHtml(identityText({ character: state.pickedCharacter, skin: state.pickedSkin }))} → ${escapeHtml(identityText(offer.identity))}</p>` : "";
  const changes = (offer.changes || []).map(change => `<article class="personal-correction-review"><h4>${escapeHtml(change.component_name)}</h4><table><thead><tr><th>Ajuste</th><th>Antes</th><th>Depois</th></tr></thead><tbody>${change.fields.map(field => `<tr><td>${escapeHtml(fieldNames[field] || field)}</td><td>${escapeHtml(fieldValue(field, change.before[field]))}</td><td>${escapeHtml(fieldValue(field, change.after[field]))}</td></tr>`).join("")}</tbody></table></article>`).join("");
  const switches = (offer.state_changes || []).length ? `<p><b>Componentes que começarão em outro estado:</b></p><ul>${offer.state_changes.map(change => `<li>${escapeHtml(change.name)}: ${change.before ? "ativo" : "desativado"} → ${change.after ? "ativo" : "desativado"}</li>`).join("")}</ul>` : "";
  const overlay = openComponentDialog("Revisar correções pessoais", `<p>Escolhas salvas em <b>${escapeHtml(offer.source_name)}</b>. Somente as mudanças abaixo serão reutilizadas nesta importação.</p>${identity}${changes}${switches}${fullBackupWarnings(offer.warnings)}<p>Os tipos continuam sendo detectados pelos arquivos. Esta escolha ainda não instala o mod.</p><button class="btn primary accept-personal-correction">Usar estas correções</button>`);
  overlay.querySelector(".accept-personal-correction").onclick = async event => {
    if (overlay.dataset.busy === "true") return;
    overlay.dataset.busy = "true"; event.target.disabled = true;
    try {
      const before = state.personalCorrectionIdentityBefore || { character: state.pickedCharacter || "Generic", skin: state.pickedSkin || "" };
      await setPersonalImportIdentity(offer.identity || before);
      state.personalCorrectionIdentityBefore = before;
      state.personalCorrectionChoice = offer.id;
      document.getElementById("install-correction-choice").value = offer.id;
      document.getElementById("install-correction-note").textContent = "Correções selecionadas. Serão aplicadas quando você instalar; editar a identidade desmarca esta escolha.";
      overlay.remove();
      document.getElementById("install-correction-choice").focus();
    } catch (error) { maintenanceError(overlay, error); event.target.disabled = false; }
    finally { overlay.dataset.busy = "false"; }
  };
}

function fullBackupWarnings(warnings = []) {
  return warnings.length ? `<div class="backup-warnings"><b>Avisos</b><ul>${warnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join("")}</ul></div>` : "";
}

function fullBackupFacts(plan) {
  const bytes = value => formatModSize((Number(value) || 0) / 1048576);
  return `<dl class="backup-facts"><div><dt>Biblioteca</dt><dd>${Number(plan.mods) || 0} mod(s) · ${Number(plan.file_count) || 0} arquivo(s)</dd></div>${plan.total_bytes == null ? "" : `<div><dt>Conteúdo</dt><dd>${bytes(plan.total_bytes)}</dd></div>`}<div><dt>Espaço necessário estimado</dt><dd>${bytes(plan.required_bytes)}</dd></div><div><dt>Disponível no destino</dt><dd>${bytes(plan.available_bytes)}</dd></div></dl>`;
}

async function prepareFullBackup(restore = false) {
  if (state.importBusy) return;
  if (pendingOperation()) { await resumeLastOperation(); return; }
  try {
    const requestId = newOperationRequest(restore ? "restore-preview" : "backup-preview");
    const result = await runImportOperation(() => restore ? api().start_full_restore_preview(requestId) : api().start_full_backup_preview(requestId),
      restore ? "Verificando backup completo" : "Estimando backup completo",
      { requestId, context: { kind: restore ? "restore_preview" : "backup_preview" } });
    if (result?.cancelled) return;
    if (!result?.ok) throw new Error(result?.error || "Não foi possível preparar o backup.");
    if (restore) showFullRestorePlan(result); else showFullBackupPlan(result);
  } catch (error) { alert(error.message); }
}

function showFullBackupPlan(plan) {
  const overlay = openComponentDialog("Criar backup completo", `<p>O ZIP incluirá catálogo, configurações, correções pessoais, arquivos privados dos mods e mídias, além do backup original de MoviesBink quando disponível.</p>${fullBackupFacts(plan)}<p><b>Destino</b></p><code>${escapeHtml(plan.destination)}\\${escapeHtml(plan.filename)}</code><p>O ZIP é salvo sem recompressão. Esta operação não altera os mods instalados.</p>${fullBackupWarnings(plan.warnings)}${plan.complete ? "" : '<label class="backup-incomplete-choice"><input type="checkbox" class="backup-allow-incomplete"> Entendo que faltam arquivos e quero criar uma cópia incompleta.</label>'}${plan.can_create ? "" : '<p class="dialog-error">Não há espaço suficiente neste destino. Feche e escolha outra pasta.</p>'}<button class="btn primary confirm-full-backup" ${plan.can_create && plan.complete ? "" : "disabled"}>Criar backup</button>`);
  const checkbox = overlay.querySelector(".backup-allow-incomplete"), button = overlay.querySelector(".confirm-full-backup");
  if (checkbox) checkbox.onchange = () => { button.disabled = !plan.can_create || !checkbox.checked; };
  button.onclick = () => void completeFullBackup(plan, false, checkbox?.checked === true, overlay);
}

function showFullRestorePlan(plan) {
  const overlay = openComponentDialog("Extrair backup completo", `<p>${escapeHtml(plan.note || "Será criada uma pasta nova. A biblioteca em uso e os arquivos do jogo não serão alterados.")}</p>${fullBackupFacts(plan)}<p><b>Nova pasta</b></p><code>${escapeHtml(plan.destination)}</code><p>Todos os arquivos serão verificados por SHA-256. A cópia será extraída com os mods desativados e sem caminho do jogo configurado.</p>${plan.complete ? "" : '<p class="backup-warnings">Este backup foi criado com arquivos ausentes; eles não poderão ser recuperados desta cópia.</p>'}${fullBackupWarnings(plan.warnings)}${plan.can_restore ? "" : '<p class="dialog-error">Não há espaço suficiente neste destino. Feche e escolha outra pasta.</p>'}<button class="btn primary confirm-full-restore" ${plan.can_restore ? "" : "disabled"}>Extrair na nova pasta</button>`);
  overlay.querySelector(".confirm-full-restore").onclick = () => void completeFullBackup(plan, true, false, overlay);
}

async function completeFullBackup(plan, restore, allowIncomplete, overlay) {
  if (state.importBusy) return;
  overlay.remove();
  try {
    const result = await runImportOperation(() => restore ? api().start_full_restore(plan.token) : api().start_full_backup(plan.token, allowIncomplete),
      restore ? "Extraindo e verificando backup" : "Criando backup completo",
      { requestId: `${restore ? "restore" : "backup"}:${plan.token}`, context: { kind: restore ? "backup_restore" : "backup_create" } });
    if (result?.cancelled) return;
    if (!result?.ok) throw new Error(result?.error || "Não foi possível concluir a operação.");
    showFullBackupResult(result, restore);
  } catch (error) { alert(error.message); }
}

function showFullBackupResult(result, restore = false) {
  openComponentDialog(restore ? "Backup extraído e verificado" : result.complete ? "Backup completo criado" : "Backup incompleto criado",
    `<p>${escapeHtml(restore ? result.note || "A biblioteca em uso foi preservada." : "A cópia foi salva no destino escolhido. Nenhum arquivo de origem foi removido.")}</p><label>Caminho da cópia<input class="modal-input" type="text" readonly value="${escapeHtml(result.path)}"></label>${restore ? '<p>Consulte <b>RESTAURACAO.md</b> nessa pasta para usar a cópia. A extração não substitui nem instala automaticamente a biblioteca atual.</p>' : ""}${fullBackupWarnings(result.warnings)}`);
}

document.getElementById("setting-full-backup").onclick = () => void prepareFullBackup();
document.getElementById("setting-full-restore").onclick = () => void prepareFullBackup(true);

async function showRelationSuggestions(mod, componentId = null) {
  const overlay = openComponentDialog("Sugestões de relações", '<p role="status">Consultando os nomes e tipos já analisados…</p>');
  try {
    const result = await api().suggest_component_relations(mod.id, componentId);
    if (!result?.ok) throw new Error(result?.error || "Não foi possível obter sugestões.");
    if (!overlay.isConnected) return;
    const suggestions = result.suggestions || [], body = document.createElement("div");
    body.innerHTML = `<p>Nomes e tipos indicam possibilidades. Confirme as instruções do autor do mod antes de criar dependências.</p>${suggestions.map((suggestion, index) => `<article class="maintenance-operation"><b>${suggestion.kind === "alternative_group" ? "Possíveis alternativas" : "Possível dependência"}</b><p>${escapeHtml((suggestion.component_names || []).join(" · "))}</p><p>${escapeHtml(suggestion.reason)}</p>${(suggestion.warnings || []).map(note => `<small>${escapeHtml(maintenanceNote(note))}</small>`).join("")}${suggestion.kind === "alternative_group" ? `<label>Variante a manter<select class="relation-preferred" aria-label="Variante a manter"><option value="">Manter a seleção atual</option>${suggestion.component_ids.map((id, position) => `<option value="${escapeHtml(id)}">${escapeHtml(suggestion.component_names?.[position] || id)}</option>`).join("")}</select></label>` : ""}<button class="btn relation-review" data-index="${index}">Revisar esta sugestão</button></article>`).join("") || '<p class="maintenance-empty">Não encontrei uma relação suficientemente clara para sugerir. Você ainda pode configurar as regras manualmente.</p>'}`;
    overlay.querySelector('[role="status"]').replaceWith(body);
    body.querySelectorAll(".relation-review").forEach(button => { button.onclick = async () => {
      button.disabled = true;
      try {
        const suggestion = suggestions[Number(button.dataset.index)], preferred = button.closest("article").querySelector("select")?.value || null;
        const plan = await api().preview_relation_suggestion(mod.id, suggestion.id, preferred);
        if (!plan?.ok) throw new Error(plan?.error || "Não foi possível preparar as relações.");
        if (overlay.isConnected) showRelationPlan(mod, plan);
      } catch (error) { maintenanceError(overlay, error); button.disabled = false; }
    }; });
  } catch (error) { maintenanceError(overlay, error); }
}

function showRelationPlan(mod, plan) {
  const names = new Map((mod.components || []).map(component => [component.id, component.name]));
  const describeRules = rules => [rules.exclusive_group ? `Grupo: ${rules.exclusive_group}` : "Sem grupo de alternativas", rules.requires?.length ? `Depende de: ${rules.requires.map(id => names.get(id) || id).join(", ")}` : "Sem dependências"].join(" · ");
  const overlay = openComponentDialog("Revisar relações e switches", `<p>${escapeHtml(plan.note)}</p><div class="maintenance-list">${plan.rule_changes.map(change => `<div class="maintenance-operation"><b>${escapeHtml(change.name)}</b><p>Antes: ${escapeHtml(describeRules(change.before))}</p><p>Depois: ${escapeHtml(describeRules(change.after))}</p></div>`).join("")}</div><p>${plan.affects_game ? "A aplicação também vai atualizar estes componentes na pasta do jogo:" : "Alterações na seleção dos componentes:"}</p><ul>${plan.state_changes.map(change => `<li>${escapeHtml(change.name)} → <b>${change.after ? "Ativar" : "Desativar"}</b></li>`).join("") || "<li>Nenhum switch será alterado.</li>"}</ul>${(plan.warnings || []).map(note => `<p>${escapeHtml(maintenanceNote(note))}</p>`).join("")}<button class="btn primary relation-apply">Confirmar relações</button><p class="relation-result" role="status"></p>`);
  overlay.querySelector(".relation-apply").onclick = async event => {
    event.target.disabled = true; overlay.dataset.busy = "true";
    try {
      const result = await api().apply_relation_suggestion(plan.token);
      if (!result?.ok) throw new Error([result?.error || "Não foi possível aplicar as relações.", ...(result?.warnings || [])].join("\n"));
      overlay.querySelector(".relation-result").textContent = "Relações aplicadas. " + (result.warnings || []).join(" ");
      await refreshMaintainedMods([mod.id]);
    } catch (error) { maintenanceError(overlay, error); }
    finally { overlay.dataset.busy = "false"; }
  };
}

async function showConflictResolver(report) {
  const owners = [...new Map((report.conflicts || []).flatMap(conflict => conflict.owners || []).map(owner => [JSON.stringify([owner.mod_id, owner.component_id]), owner])).values()];
  const overlay = openComponentDialog("Escolher o que manter", `<p>Esta ação usa os conflitos encontrados pelo detector. Nada será alterado antes de você revisar as desativações.</p><label>Manter ativo<select class="conflict-keep" aria-label="Componente a manter">${owners.map((owner, index) => `<option value="${index}">${escapeHtml(owner.mod)} · ${escapeHtml(owner.component)}</option>`).join("")}</select></label><button class="btn primary conflict-preview-choice">Revisar desativações</button>`);
  overlay.querySelector(".conflict-preview-choice").onclick = async event => {
    event.target.disabled = true;
    try {
      const owner = owners[Number(overlay.querySelector("select").value)];
      const plan = await api().preview_conflict_resolution(owner.mod_id, owner.component_id);
      if (!plan?.ok) throw new Error(plan?.error || "Não foi possível revisar a escolha.");
      if (overlay.isConnected) showConflictResolutionPlan(plan);
    } catch (error) { maintenanceError(overlay, error); event.target.disabled = false; }
  };
}

function showConflictResolutionPlan(plan) {
  const reasonNames = { conflict:"Conflito detectado", dependency:"Depende de um componente que será desativado", manual_conflict:"Conflito marcado manualmente" };
  const overlay = openComponentDialog("Revisar desativações", `<p>Manter: <b>${escapeHtml(plan.keep.mod)} · ${escapeHtml(plan.keep.component)}</b></p><p>${escapeHtml(plan.note)}</p><div class="maintenance-list">${plan.changes.map(change => `<div class="maintenance-operation"><b>${escapeHtml(change.mod)} · ${escapeHtml(change.component)}</b><p>Desativar · ${escapeHtml(reasonNames[change.reason] || change.reason || "Concorrente")}</p></div>`).join("") || '<p class="maintenance-empty">Nenhuma desativação necessária.</p>'}</div>${(plan.warnings || []).map(note => `<p>${escapeHtml(maintenanceNote(note))}</p>`).join("")}<button class="btn primary conflict-apply-choice" ${plan.changes.length ? "" : "disabled"}>Confirmar desativações</button><p class="conflict-apply-result" role="status"></p>`);
  overlay.querySelector(".conflict-apply-choice").onclick = async event => {
    event.target.disabled = true; overlay.dataset.busy = "true";
    try {
      const result = await api().apply_conflict_resolution(plan.token);
      if (!result?.ok) throw new Error([result?.error || "Não foi possível aplicar a escolha.", ...(result?.errors || []), result?.recovery_pending ? "Consulte Operações interrompidas nas configurações." : ""].filter(Boolean).join("\n"));
      overlay.querySelector(".conflict-apply-result").textContent = "Escolha aplicada. " + (result.warnings || []).join(" ");
      state.conflictRefreshInProgress = true;
      await refreshMaintainedMods(result.changed || []);
      const fresh = await api().get_conflicts();
      if (fresh?.ok) { cacheConflictIndicators(fresh.conflicts); renderMods(); if (document.getElementById("conflicts-overlay")) showConflictResults(fresh); }
    } catch (error) { maintenanceError(overlay, error); }
    finally { overlay.dataset.busy = "false"; state.conflictRefreshInProgress = false; void refreshOperationNotice(); }
  };
}
document.getElementById("library-health-result").onclick = async event => {
  const button = event.target.closest("[data-health-repair], [data-health-ignore]");
  if (!button || button.disabled || !lastLibraryHealth) return;
  const index = Number(button.dataset.healthRepair ?? button.dataset.healthIgnore), issue = lastLibraryHealth.issues[index];
  if (!issue) return;
  const id = issue.mod_id || issue.id;
  if (button.dataset.healthRepair !== undefined) { await showLibraryRepair(id); return; }
  if (!confirm("Ignorar esta mídia ausente? Nenhum arquivo será apagado; ela deixará de aparecer como pendência.")) return;
  button.disabled = true;
  try {
    const result = await api().ignore_missing_media(id, issue.missing_media);
    if (!result?.ok) throw new Error(result?.error || "Não foi possível ignorar a mídia.");
    await refreshLibraryHealthMod(id);
  } catch (error) { alert(error.message); button.disabled = false; }
};
