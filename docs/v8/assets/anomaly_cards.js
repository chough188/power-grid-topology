(function () {
  const ANOMALY_CARDS = [
    {id:"topo_interrupt", cn:"Topology break"},
    {id:"virtual_faulty", cn:"Virtual fault"},
    {id:"model_mismatch", cn:"Model mismatch"},
    {id:"ghost_topology", cn:"Ghost topology"},
    {id:"topo_obfuscation", cn:"Topology obfuscation"},
    {id:"telemetry_mismatch", cn:"Telemetry mismatch"},
    {id:"signal_mismatch", cn:"Signal mismatch"},
    {id:"measurement_outlier", cn:"Outlier"},
    {id:"stale_data", cn:"Stale data"},
    {id:"measurement_bias", cn:"Bias"},
    {id:"duplicate_measurement", cn:"Duplicate"},
    {id:"parameter_error", cn:"Param error"},
    {id:"impedance_degradation", cn:"Z-degrade"},
    {id:"bypass_operation", cn:"Bypass"},
    {id:"load_transfer_residual", cn:"Transfer residual"},
    {id:"load_shift", cn:"Load shift"},
    {id:"reverse_power_flow", cn:"Reverse flow"},
    {id:"branch_contingency", cn:"N-1 fail"},
    {id:"bus_section_mismatch", cn:"Bus section"},
    {id:"voltage_collapse", cn:"V collapse"},
    {id:"voltage_regulation", cn:"V regulation"},
    {id:"dg_intermittent", cn:"DG intermittent"},
    {id:"communication_loss", cn:"Comms loss"},
    {id:"protection_misconfig", cn:"Protection"},
    {id:"trafo_tap_fault", cn:"Tap fault"},
    {id:"grounding_fault", cn:"Ground fault"},
    {id:"clock_drift", cn:"Clock drift"},
    {id:"harmonic_pollution", cn:"Harmonic"}
  ];
  const IMG_BASE = "/assets/ai_cards/";  // Doubao AI 实图
  function fallbackEmoji(id) {
    // 纯 SVG 语义图标 (无 emoji, 符合 frontend-dev 规范); 仅当 AI 实图加载失败时回退显示
    return '<svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"/></svg>';
  }
  function renderCards() {
    var g = document.getElementById("cards-grid");
    if (!g) return;
    g.innerHTML = ANOMALY_CARDS.map(function(c){
      return '<div class="card anomaly-card" data-id="'+c.id+'" style="padding:0;overflow:hidden;cursor:pointer">'+
        '<div style="position:relative;aspect-ratio:1;background:linear-gradient(135deg,#0f172a,#1e3a8a);display:flex;align-items:center;justify-content:center;font-size:42px">'+
        '<img src="'+IMG_BASE+c.id+'.jpg" alt="'+c.cn+'" loading="lazy" style="width:100%;height:100%;object-fit:cover;position:absolute;inset:0" onerror="this.style.display=String.fromCharCode(110,111,110,101);this.parentNode.querySelector(String.fromCharCode(46,102,98)).style.display=String.fromCharCode(102,108,101,120)">'+
        '<span class="fb" style="display:none;width:100%;height:100%;align-items:center;justify-content:center;color:#fff;font-size:42px">'+fallbackEmoji(c.id)+'</span>'+
        '</div>'+
        '<div style="padding:8px 12px;font-size:12px;font-weight:600">'+
        c.cn+'<span style="color:var(--fg-muted);font-weight:400;font-size:10px"> '+c.id+'</span>'+
        '</div></div>';
    }).join("");
    g.querySelectorAll(".anomaly-card").forEach(function(el){
      el.addEventListener("click", function(){
        var id = el.dataset.id;
        var tab = document.getElementById("tab-table"); if (tab) tab.click();
        var sel = document.getElementById("filter-type"); if (sel) sel.value = id;
        setTimeout(function(){ var b=document.getElementById("btn-detect"); if(b) b.click(); }, 200);
      });
    });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", renderCards);
  else renderCards();
})();