"""
MemoLibDev — V0.2 : Interface conversationnelle non-technique (front natif)
===========================================================================

Front MINIMAL (HTML/CSS/JS natif, zéro dépendance) posé AU-DESSUS de l'API
façade déjà validée (api_facade), EXACTEMENT comme web_mvp : il n'ajoute
AUCUN serveur, AUCUNE route, AUCUNE capacité d'exécution. Il TRADUIT les
états réels du serveur en états humains (contrat human_states) et affiche
l'analyse explicative (analysis_builder) de façon compréhensible.

RÈGLES GRAVÉES :
    - le navigateur est NON AUTORITAIRE : il n'autorise rien, ne décide
      d'aucune transition, ne déclare jamais seul « terminé » / « réussi » ;
    - toute transition d'état vient du SERVEUR (api_facade), seul juge ;
    - « Agir » réutilise le parcours existant (/mission SUPERVISED_APPLY ->
      AWAITING_AUTHORIZATION -> aperçu -> /approve|/reject). AUCUNE nouvelle
      capacité n'est créée pour ce bouton ;
    - détails techniques (SHA, D5.8/D5.9, chemins internes) masqués par
      défaut, derrière « Voir les détails techniques » ;
    - supprimer ce front ne retire AUCUNE protection du Core (prouvé).

Le contrat d'états humains est dupliqué en JS en LECTURE SEULE (miroir du
module Python human_states) : le JS ne fait que TRADUIRE un `state` reçu ;
il ne fabrique jamais d'état. Les tests vérifient la cohérence.
"""

from __future__ import annotations

from typing import Optional, Tuple


_INDEX_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MemoLibDev</title>
<style>
  :root { --bg:#0f1115; --card:#171a21; --ink:#e8eaed; --muted:#9aa0a6;
          --accent:#4c8bf5; --ok:#36b37e; --warn:#e0a106; --err:#e5484d;
          --line:#262b33; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.5 system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }
  .wrap { max-width:760px; margin:0 auto; padding:48px 20px 96px; }
  h1 { font-size:22px; font-weight:600; margin:0 0 20px; }
  label { display:block; color:var(--muted); font-size:14px; margin:0 0 8px; }
  textarea { width:100%; min-height:92px; resize:vertical; padding:14px;
             border-radius:12px; border:1px solid var(--line);
             background:var(--card); color:var(--ink); font:inherit; }
  .actions { display:flex; gap:12px; margin:16px 0 0; flex-wrap:wrap; }
  button { cursor:pointer; border:1px solid var(--line); background:var(--card);
           color:var(--ink); padding:12px 18px; border-radius:12px;
           font:inherit; font-weight:600; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; }
  button.danger { background:transparent; border-color:var(--err); color:var(--err); }
  button:disabled { opacity:.45; cursor:not-allowed; }
  .hint { color:var(--muted); font-size:13px; margin:8px 0 0; }

  /* Progression */
  .progress { display:flex; flex-wrap:wrap; gap:10px 18px; margin:22px 0 4px;
              padding:14px 16px; background:var(--card);
              border:1px solid var(--line); border-radius:12px; }
  .step { display:flex; align-items:center; gap:8px; font-size:14px;
          color:var(--muted); }
  .step .dot { width:16px; text-align:center; }
  .step.done { color:var(--ok); }
  .step.current { color:var(--ink); font-weight:600; }
  .step.todo { color:var(--muted); opacity:.65; }

  /* État humain courant */
  .state-banner { margin-top:18px; padding:14px 16px; border-radius:12px;
                  background:var(--card); border:1px solid var(--line);
                  font-size:16px; display:flex; align-items:center; gap:10px; }
  .state-banner.ok   { border-color:rgba(54,179,126,.5); }
  .state-banner.warn { border-color:rgba(224,161,6,.5); }
  .state-banner.err  { border-color:rgba(229,72,77,.5); }

  .card { margin-top:18px; background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:18px; }
  .card h2 { font-size:14px; margin:0 0 12px; color:var(--muted);
             text-transform:uppercase; letter-spacing:.04em; }
  .field { margin:10px 0; }
  .field .k { color:var(--muted); font-size:13px; }
  .field .v { white-space:pre-wrap; }
  ul.facts, ul.list { margin:6px 0 0; padding-left:18px; }
  ul.facts li { margin:4px 0; }
  .fact-src { color:var(--muted); font-size:12px; }
  .conf { display:inline-block; padding:2px 10px; border-radius:999px;
          font-size:12px; font-weight:600; margin-left:6px; }
  .conf.HIGH { background:rgba(54,179,126,.15); color:var(--ok); }
  .conf.MEDIUM { background:rgba(224,161,6,.15); color:var(--warn); }
  .conf.LOW { background:rgba(229,72,77,.15); color:var(--err); }
  .nomod { margin-top:12px; color:var(--ok); font-size:14px; }
  .warn-box { margin:14px 0; padding:12px 14px; border-radius:10px;
              background:rgba(224,161,6,.1); border:1px solid rgba(224,161,6,.4);
              color:#f0c868; }
  .approve { margin-top:16px; padding-top:16px; border-top:1px solid var(--line); }
  input[type=text] { width:100%; padding:12px; border-radius:10px;
                     border:1px solid var(--line); background:var(--bg);
                     color:var(--ink); font:inherit; }
  .row { display:flex; gap:12px; margin-top:12px; flex-wrap:wrap; }
  details.tech { margin-top:14px; border-top:1px dashed var(--line);
                 padding-top:10px; }
  details.tech summary { cursor:pointer; color:var(--muted); font-size:13px; }
  details.tech pre { white-space:pre-wrap; word-break:break-word;
                     font-size:12px; color:var(--muted); }
  .spinner { color:var(--muted); font-size:14px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Que voulez-vous faire&nbsp;?</h1>
  <label for="mission">Décrivez votre demande en langage courant</label>
  <textarea id="mission" placeholder="Ex. : Pourquoi ma page de connexion ne fonctionne pas ?"></textarea>

  <div class="actions">
    <button id="btn-comprendre">Comprendre</button>
    <button id="btn-proposer">Proposer</button>
    <button id="btn-agir" class="primary">Agir</button>
  </div>
  <p class="hint">« Agir » <strong>prépare</strong> une action&nbsp;; rien
     n'est appliqué sans votre autorisation explicite.</p>

  <div id="out"></div>
</div>

<script>
"use strict";
// =====================================================================
// Le navigateur est NON AUTORITAIRE. Il TRADUIT un état renvoyé par le
// serveur. Il n'invente aucun état, ne décide d'aucune autorisation, et
// ne déclare jamais seul « terminé » / « réussi ». Toute transition et
// toute décision de sécurité appartiennent au serveur/Core.
// =====================================================================

const CLIENT_TIMEOUT_MS = 120000;

// --- Miroir LECTURE SEULE du contrat human_states (Python). Le JS ne
//     fabrique pas d'état : il traduit un `state` reçu du serveur. ---
const HUMAN_STATES = {
  UNDERSTANDING:     "Je comprends votre demande",
  INSPECTING:        "J'examine votre projet",
  VERIFYING:         "Je vérifie les éléments importants",
  ANALYZING:         "J'analyse ce que j'ai trouvé",
  ANALYZED:          "Analyse terminée",
  PROPOSING:         "Je prépare une proposition",
  AWAITING_APPROVAL: "Votre décision est nécessaire",
  EXECUTING:         "J'effectue l'action",
  VERIFYING_RESULT:  "Je vérifie le résultat",
  COMPLETED:         "Terminé",
  REFUSED:           "L'action a été refusée",
  BLOCKED:           "Je me suis arrêté pour votre sécurité",
  ROLLED_BACK:       "La modification a été annulée et l'état a été vérifié",
  FAILED:            "L'action n'a pas pu être terminée",
};
const SERVER_TO_HUMAN = {
  ANALYZING:"ANALYZING", PROPOSAL_READY:"ANALYZED",
  AWAITING_AUTHORIZATION:"AWAITING_APPROVAL", AUTHORIZED:"EXECUTING",
  EXECUTING:"EXECUTING", VERIFYING:"VERIFYING_RESULT", COMPLETED:"COMPLETED",
  REFUSED:"REFUSED", BLOCKED:"BLOCKED", FAILED:"FAILED",
  ROLLED_BACK:"ROLLED_BACK", QUESTION:"UNDERSTANDING",
  ANALYZED:"ANALYZED", AWAIT_HUMAN:"AWAITING_APPROVAL", APPLIED:"COMPLETED",
  NO_PATCH_POSSIBLE:"BLOCKED", OK:"ANALYZED", ERROR:"FAILED",
};
const NEGATIVE = new Set(["REFUSED","BLOCKED","FAILED","ROLLED_BACK"]);
const SUCCESS  = new Set(["ANALYZED","COMPLETED"]);
const PROGRESS = [
  ["COMPRENDRE","Comprendre"], ["EXAMINER","Examiner"], ["ANALYSER","Analyser"],
  ["PROPOSER","Proposer"], ["DECIDER","Décider"], ["EXECUTER","Exécuter"],
  ["VERIFIER","Vérifier le résultat"],
];
const STEP_INDEX = {
  UNDERSTANDING:0, INSPECTING:1, VERIFYING:1, ANALYZING:2, ANALYZED:2,
  PROPOSING:3, AWAITING_APPROVAL:4, EXECUTING:5, VERIFYING_RESULT:6,
  COMPLETED:6, REFUSED:4, BLOCKED:2, ROLLED_BACK:6, FAILED:5,
};

// Fail-safe : état inconnu/absent -> FAILED (jamais un faux succès).
function toHuman(serverState) {
  if (!serverState || typeof serverState !== "string") return "FAILED";
  return SERVER_TO_HUMAN[serverState.trim()] || "FAILED";
}

const out = document.getElementById("out");
const missionEl = document.getElementById("mission");
const allButtons = ["btn-comprendre","btn-proposer","btn-agir"]
  .map(id => document.getElementById(id));

let busy = false;
let currentRunId = null;      // jamais montré à l'utilisateur

function setBusy(v){ busy = v; allButtons.forEach(b => b.disabled = v); }
function el(tag, cls, text){ const n=document.createElement(tag);
  if(cls) n.className=cls; if(text!=null) n.textContent=text; return n; }
function clearOut(){ out.innerHTML=""; }
function showLoading(label){ clearOut(); out.appendChild(el("div","spinner","… "+label)); }
function missionText(){ return (missionEl.value||"").trim(); }

// --- Progression dérivée de l'ÉTAT RÉEL (jamais animée) ---
function renderProgress(human){
  const idx = (human in STEP_INDEX) ? STEP_INDEX[human] : 0;
  const success = SUCCESS.has(human);
  const box = el("div","progress");
  PROGRESS.forEach(([key,label], i) => {
    let status;
    if (i < idx) status = "done";
    else if (i === idx) status = success ? "done" : "current";
    else status = "todo";
    const s = el("div","step "+status);
    s.appendChild(el("span","dot", status==="done" ? "✓" : (status==="current" ? "●" : "○")));
    s.appendChild(el("span",null,label));
    box.appendChild(s);
  });
  return box;
}

function renderStateBanner(human){
  const negative = NEGATIVE.has(human);
  const success = SUCCESS.has(human);
  const cls = negative ? "err" : (success ? "ok" : "warn");
  const icon = negative ? "🛑" : (success ? "✅" : "⏳");
  const b = el("div","state-banner "+cls);
  b.appendChild(el("span",null,icon));
  b.appendChild(el("span",null, HUMAN_STATES[human] || HUMAN_STATES.FAILED));
  return b;
}

function field(parent,k,v){
  if(v==null || v==="" || (Array.isArray(v)&&v.length===0)) return;
  const f=el("div","field"); f.appendChild(el("div","k",k));
  if(Array.isArray(v)){ const ul=el("ul","list");
    v.forEach(x=>ul.appendChild(el("li",null,String(x)))); f.appendChild(ul); }
  else f.appendChild(el("div","v",String(v)));
  parent.appendChild(f);
}

// --- Rendu de l'analyse (ANALYZED) : données humaines, technique masqué ---
function renderAnalysis(data, human){
  clearOut();
  out.appendChild(renderProgress(human));
  out.appendChild(renderStateBanner(human));

  const vue = data.vue || {};
  const an = (vue.analysis) || null;   // AnalysisResult sérialisé si exposé
  const card = el("div","card");
  card.appendChild(el("h2",null,"Analyse"));

  // Champs humains (depuis vue humanisée OU AnalysisResult).
  field(card,"Demande comprise", an ? an.demande_comprise : vue.ce_que_j_ai_compris);
  if (an && Array.isArray(an.elements_examines))
    field(card,"Éléments examinés", an.elements_examines);

  // Faits vérifiés (chacun sourcé) — technique utile mais lisible.
  if (an && Array.isArray(an.faits_verifies) && an.faits_verifies.length){
    const f=el("div","field"); f.appendChild(el("div","k","Faits vérifiés"));
    const ul=el("ul","facts");
    an.faits_verifies.forEach(x=>{
      const li=el("li");
      li.appendChild(el("span",null, x.extrait || ""));
      const lignes = Array.isArray(x.lignes) ? x.lignes.join("–") : "";
      const src = `${x.fichier||""}${lignes?(" : lignes "+lignes):""}`;
      li.appendChild(el("div","fact-src", src));
      ul.appendChild(li);
    });
    f.appendChild(ul); card.appendChild(f);
  }

  field(card,"Analyse", an ? an.analyse : vue.resultat);

  // Cause probable : si null, on l'affiche comme indéterminée (jamais inventée).
  if (an){
    field(card,"Cause probable",
          an.cause_probable != null ? an.cause_probable
          : "Non déterminée — les preuves disponibles sont insuffisantes.");
    if (an.correction_minimale != null)
      field(card,"Correction minimale (descriptive)", an.correction_minimale);
    // Confiance avec pastille.
    const cf=el("div","field"); cf.appendChild(el("div","k","Niveau de confiance"));
    const span=el("span","conf "+(an.confiance||"LOW"), an.confiance||"LOW");
    const w=el("div"); w.appendChild(span); cf.appendChild(w); card.appendChild(cf);
    if (Array.isArray(an.incertitudes) && an.incertitudes.length)
      field(card,"Incertitudes", an.incertitudes);
  }

  // Confirmation : aucune modification.
  card.appendChild(el("div","nomod","✓ Aucune modification n'a été effectuée."));

  // V0.3 : si le Core a produit une proposition descriptive (diff candidat),
  // on l'affiche ici aussi — LECTURE SEULE, serveur comme seule source.
  const proposal = (vue.proposal) || null;
  if (proposal) renderProposalBlock(card, proposal);

  // Détails techniques : MASQUÉS par défaut.
  const det=el("details","tech");
  det.appendChild(el("summary",null,"Voir les détails techniques"));
  const pre=el("pre",null, JSON.stringify(vue.technique || an || {}, null, 2));
  det.appendChild(pre);
  card.appendChild(det);

  out.appendChild(card);
}

// --- Rendu d'aperçu « Agir » (AWAITING_APPROVAL) ---
function renderAgirPreview(data, human){
  clearOut();
  out.appendChild(renderProgress(human));
  out.appendChild(renderStateBanner(human));
  const vue = data.vue || {}, preview = data.preview || {};
  const card = el("div","card");
  card.appendChild(el("h2",null,"Voici ce que mon agent propose de faire"));
  field(card,"Fichier concerné", preview.fichier_concerne);
  field(card,"Pourquoi", preview.pourquoi || vue.pourquoi);
  field(card,"Résultat attendu", preview.resultat_attendu || vue.resultat);

  // V0.3 : la PROPOSITION descriptive vient UNIQUEMENT du serveur/Core.
  // Le navigateur ne recalcule RIEN (diff/SHA/lignes) : il affiche ce que
  // le Core a produit. Absente => aucun aperçu fabriqué.
  const proposal = (vue.proposal) || (preview.proposal) || null;
  if (proposal) renderProposalBlock(card, proposal);

  // L'autorisation n'est proposée QUE si le SERVEUR le permet.
  if (data.can_approve){
    card.appendChild(el("div","warn-box",
      "⚠️ Cette action modifiera votre projet. Elle ne sera exécutée "
      + "qu'après votre autorisation explicite."));
    const ap=el("div","approve");
    ap.appendChild(el("div","k","Pour autoriser, saisissez votre nom :"));
    const name=el("input"); name.type="text"; name.placeholder="Nom de l'approbateur";
    ap.appendChild(name);
    const row=el("div","row");
    const refuse=el("button","danger","Refuser"); refuse.addEventListener("click",runReject);
    const allow=el("button","primary","Autoriser");
    allow.addEventListener("click",()=>runApprove(name.value));
    row.appendChild(refuse); row.appendChild(allow); ap.appendChild(row);
    ap.appendChild(el("p","hint",
      "Votre nom enregistre votre décision ; il n'accorde aucun pouvoir. "
      + "Le moteur reste seul juge et peut refuser."));
    card.appendChild(ap);
  } else {
    field(card,"Résultat", vue.resultat);
  }
  out.appendChild(card);
}

// --- Rendu de la PROPOSITION (V0.3) — LECTURE SEULE, NON AUTORITAIRE ---
// N'affiche QUE des données reçues du serveur (proposal.*). Ne recalcule
// NI diff NI SHA. Les informations techniques sensibles (SHA, lignes
// exactes, provenance) sont masquées derrière « Voir les détails techniques ».
function renderProposalBlock(card, p){
  field(card,"Résumé", p.summary);
  field(card,"Pourquoi (proposition)", p.reason);

  // Confiance : si null, affichée comme non disponible (jamais inventée).
  // Le front NE CALCULE JAMAIS la confiance et NE PEUT PAS la modifier :
  // il n'affiche que p.confidence (niveau) + p.confidence_reasons/gates
  // fournis par le SERVEUR. Il ne peut pas transformer LOW en HIGH.
  const CONF_LABEL = { HIGH:"Confiance élevée", MEDIUM:"Confiance moyenne",
                       LOW:"Confiance faible" };
  const CONF_SENTENCE = {
    HIGH:"Les éléments observés sont cohérents et suffisamment étayés dans le périmètre analysé.",
    MEDIUM:"Plusieurs éléments concordent, mais certaines informations restent à confirmer.",
    LOW:"Les éléments disponibles ne permettent pas encore de soutenir suffisamment cette conclusion.",
  };
  const cf=el("div","field"); cf.appendChild(el("div","k","Confiance"));
  if (p.confidence){
    const span=el("span","conf "+p.confidence, CONF_LABEL[p.confidence]||p.confidence);
    const w=el("div"); w.appendChild(span); cf.appendChild(w);
    if (CONF_SENTENCE[p.confidence])
      cf.appendChild(el("div","v", CONF_SENTENCE[p.confidence]));
  } else {
    cf.appendChild(el("div","v","Non disponible — aucune mesure de confiance n'a été produite."));
  }
  card.appendChild(cf);

  // « Pourquoi cette confiance ? » — raisons + gates fournis par le serveur.
  const reasons = Array.isArray(p.confidence_reasons) ? p.confidence_reasons : [];
  const gates   = Array.isArray(p.confidence_gates) ? p.confidence_gates : [];
  if (reasons.length || gates.length){
    const det=el("details","tech");
    det.appendChild(el("summary",null,"Pourquoi cette confiance ?"));
    if (reasons.length){
      det.appendChild(el("div","k","Éléments pris en compte"));
      const ul=el("ul","list");
      reasons.forEach(x=>ul.appendChild(el("li",null,String(x))));
      det.appendChild(ul);
    }
    if (gates.length){
      det.appendChild(el("div","k","Règles de sécurité appliquées"));
      const ul=el("ul","list");
      gates.forEach(x=>ul.appendChild(el("li",null,String(x))));
      det.appendChild(ul);
    }
    card.appendChild(det);
  }

  field(card,"Risque", p.risk != null ? p.risk : "Non disponible");
  field(card,"Réversible",
        p.reversible === true ? "Oui"
        : (p.reversible === false ? "Non" : "Non déterminé"));

  // Fichiers concernés (chemin + changement proposé). SHA/lignes -> technique.
  if (Array.isArray(p.files) && p.files.length){
    const f=el("div","field"); f.appendChild(el("div","k","Fichiers concernés"));
    const ul=el("ul","facts");
    p.files.forEach(file=>{
      const li=el("li");
      li.appendChild(el("span",null, file.path || ""));
      if (file.proposed_change)
        li.appendChild(el("div","fact-src","Changement proposé : "+file.proposed_change));
      if (file.current_excerpt){
        const pre=el("pre",null, file.current_excerpt);
        pre.style.marginTop="6px"; li.appendChild(pre);
      }
      ul.appendChild(li);
    });
    f.appendChild(ul); card.appendChild(f);
  }

  // Changement proposé : aperçu du diff RÉEL du Core (jamais recalculé ici).
  if (p.diff_preview){
    const df=el("div","field");
    df.appendChild(el("div","k","Changement proposé (aperçu du diff)"));
    df.appendChild(el("pre",null, p.diff_preview));
    card.appendChild(df);
  } else {
    field(card,"Changement proposé","Aucun diff produit par le moteur.");
  }

  // Autorisation humaine requise (DESCRIPTIF : le front n'autorise rien).
  if (p.requires_human_approval)
    card.appendChild(el("div","warn-box",
      "👤 Votre autorisation est nécessaire. Le navigateur n'autorise rien : "
      + "l'application reste décidée et exécutée par le moteur contrôlé."));

  // Détails techniques (SHA, lignes exactes, provenance) — MASQUÉS par défaut.
  const det=el("details","tech");
  det.appendChild(el("summary",null,"Voir les détails techniques"));
  const tech = {
    mission_id: p.mission_id, scope: p.scope, evidence: p.evidence,
    files: Array.isArray(p.files) ? p.files.map(f=>({
      path:f.path, sha_before:f.sha_before, lines:f.lines })) : [],
  };
  det.appendChild(el("pre",null, JSON.stringify(tech, null, 2)));
  card.appendChild(det);
}


// --- Rendu terminal (COMPLETED/REFUSED/BLOCKED/FAILED/ROLLED_BACK) ---
function renderTerminal(data, human){
  clearOut();
  out.appendChild(renderProgress(human));
  out.appendChild(renderStateBanner(human));
  const vue = data.vue || {};
  const card = el("div","card");
  const negative = NEGATIVE.has(human);

  if (human === "COMPLETED"){
    card.appendChild(el("h2",null,"Résultat"));
    field(card,null,"✓ Modification effectuée");
    field(card,null,"✓ Vérification réussie");
  } else if (human === "ROLLED_BACK"){
    card.appendChild(el("h2",null,"Modification annulée"));
    field(card,null,"Une modification a rencontré un problème. "
      + "Elle a été annulée et l'état du projet a été vérifié.");
  } else if (negative){
    card.appendChild(el("h2",null, HUMAN_STATES[human]));
    field(card,null,"Aucune modification n'a été effectuée.");
  }
  field(card,"Détail", vue.resultat);
  out.appendChild(card);
}

async function callApi(path, body){
  const ctrl=new AbortController();
  const timer=setTimeout(()=>ctrl.abort(), CLIENT_TIMEOUT_MS);
  try {
    const resp=await fetch(path,{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body), signal:ctrl.signal});
    const data=await resp.json().catch(()=>({}));
    return {httpStatus:resp.status, data};
  } finally { clearTimeout(timer); }
}

function renderError(payload){
  clearOut();
  const card=el("div","card");
  card.appendChild(el("h2",null,"Erreur"));
  field(card,"Détail",(payload && payload.reason) || "Requête invalide.");
  out.appendChild(card);
}

// COMPRENDRE / PROPOSER
async function runMission(mode, titre){
  if(busy) return;
  const mission=missionText();
  if(!mission){ renderError({reason:"Décrivez d'abord votre demande."}); return; }
  setBusy(true); showLoading(titre+" en cours");
  try {
    const {httpStatus,data}=await callApi("/mission",{mission,mode});
    if(httpStatus!==200){ renderError(data); return; }
    currentRunId=data.run_id||null;
    const human=toHuman(data.state || data.status);
    // V0.3 : « Proposer » (PROPOSE) remonte une proposition descriptive et
    // s'arrête en attente d'autorisation (AWAITING_APPROVAL). On l'affiche
    // via l'aperçu de proposition. « Comprendre » (READ_ONLY) reste une
    // analyse. Dans les deux cas, l'affichage ne vient QUE du serveur.
    if (human==="AWAITING_APPROVAL") renderAgirPreview(data, human);
    else renderAnalysis(data, human);
  } catch(e){
    renderError({reason:(e&&e.name==="AbortError")
      ? "La demande a pris trop de temps et a été interrompue. Réessayez."
      : "Problème de communication avec l'agent."});
  } finally { setBusy(false); }
}

// AGIR : prépare (SUPERVISED_APPLY) et s'arrête AVANT écriture (serveur).
async function runAgirPreview(){
  if(busy) return;
  const mission=missionText();
  if(!mission){ renderError({reason:"Décrivez d'abord votre demande."}); return; }
  setBusy(true); showLoading("Préparation de l'action"); currentRunId=null;
  try {
    const {httpStatus,data}=await callApi("/mission",{mission,mode:"SUPERVISED_APPLY"});
    if(httpStatus!==200){ renderError(data); return; }
    currentRunId=data.run_id||null;
    const human=toHuman(data.state || data.status);
    if(human==="AWAITING_APPROVAL") renderAgirPreview_(data, human);
    else renderTerminal(data, human);   // BLOCKED/FAILED/... selon le serveur
  } catch(e){
    renderError({reason:(e&&e.name==="AbortError")
      ? "La préparation a pris trop de temps et a été interrompue. Réessayez."
      : "Problème de communication avec l'agent."});
  } finally { setBusy(false); }
}
function renderAgirPreview_(data, human){ renderAgirPreview(data, human); }

async function runApprove(approver){
  if(busy) return;
  const name=(approver||"").trim();
  if(!name){ renderError({reason:"Saisissez un nom pour autoriser."}); return; }
  if(!currentRunId){ renderError({reason:"Préparez d'abord une action (Agir)."}); return; }
  setBusy(true); showLoading("Autorisation et exécution contrôlée");
  try {
    const {httpStatus,data}=await callApi("/approve",{run_id:currentRunId,approver:name});
    if(httpStatus!==200){ renderError(data); return; }
    const human=toHuman(data.state || data.status);
    renderTerminal(data, human);
  } catch(e){
    renderError({reason:(e&&e.name==="AbortError")
      ? "L'exécution a pris trop de temps côté client. Vérifiez le résultat avant de réessayer."
      : "Problème de communication avec l'agent."});
  } finally { setBusy(false); }
}

async function runReject(){
  if(busy) return;
  if(!currentRunId){ renderError({reason:"Rien à refuser."}); return; }
  setBusy(true); showLoading("Annulation");
  try {
    const {data}=await callApi("/reject",{run_id:currentRunId});
    const human=toHuman((data && data.state) || "REFUSED");
    renderTerminal(data||{}, human);
    currentRunId=null;
  } catch(e){
    renderError({reason:"Problème de communication avec l'agent."});
  } finally { setBusy(false); }
}

document.getElementById("btn-comprendre")
  .addEventListener("click",()=>runMission("READ_ONLY","Comprendre"));
document.getElementById("btn-proposer")
  .addEventListener("click",()=>runMission("PROPOSE","Proposer"));
document.getElementById("btn-agir").addEventListener("click",runAgirPreview);
</script>
</body>
</html>
"""


def static_provider(path: str) -> Optional[Tuple[str, bytes]]:
    """
    Sert la page unique de l'interface conversationnelle. Lecture seule,
    octets statiques, AUCUNE logique de sécurité. Toute autre route -> None.
    """
    clean = (path or "/").split("?", 1)[0].split("#", 1)[0]
    if clean in ("/", "/index.html"):
        return ("text/html; charset=utf-8", _INDEX_HTML.encode("utf-8"))
    return None


def serve_ui(host: str = "127.0.0.1", port: int = 8765, facade=None) -> None:
    """
    Lance l'API façade AVEC le front conversationnel (GET / => écran
    unique). La sécurité, les états et /mission|/approve|/reject restent
    STRICTEMENT ceux d'api_facade. Aucun serveur concurrent, aucune route
    nouvelle, aucune capacité nouvelle.
    """
    from api_facade import serve, ApiFacade
    serve(host=host, port=port, facade=facade or ApiFacade(),
          static_provider=static_provider)


if __name__ == "__main__":
    serve_ui()
