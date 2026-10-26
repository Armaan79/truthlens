$(function(){
const $text=$("#newsText"),$result=$("#result"),$count=$("#charCount"),$url=$("#urlText"),$urlResult=$("#urlResult");
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const safeLink=u=>/^https?:\/\//i.test(u||"")?esc(u):"#";
let last=null,busy=false;

/* ---------- page load, scroll, nav ---------- */
const intro=()=>$("#pageLoader").delay(200).fadeOut(400,()=>$(".fade-up").each((i,el)=>$(el).delay(i*150).queue(n=>{$(el).addClass("in");n()})));
document.readyState==="complete"?intro():$(window).on("load",intro); // load may fire before this runs
$(window).on("scroll",function(){
    const y=$(this).scrollTop();
    $(".navbar").toggleClass("scrolled",y>10);
    y>500?$("#toTop").fadeIn(200):$("#toTop").fadeOut(200);
    let cur="home";$("section[id]").each(function(){if($(this).offset().top-120<=y)cur=this.id});
    $(".nav-links a").removeClass("active").filter(`[href="#${cur}"]`).addClass("active");
});
$(".nav-links a").on("click",function(e){
    e.preventDefault();const id=$(this).attr("href");
    $("html,body").stop().animate({scrollTop:$(id).offset().top-80},600,()=>$(id==="#url-checker"?"#urlText":id==="#checker"?"#newsText":null).trigger("focus"));
});
$("#toTop").on("click",()=>$("html,body").animate({scrollTop:0},600));

function toast(msg,type=""){$("#toast").stop(true,true).attr("class",type).text(msg).fadeIn(200).delay(2200).fadeOut(300)}
function shake($el){$el.removeClass("shake");void $el[0].offsetWidth;$el.addClass("shake")}

/* ---------- loaders ---------- */
function loader($box,steps){
    $box.stop(true,true).html(`<div class="scan"><div class="scan-doc"><i></i><i></i><i></i><i></i><span class="beam"></span></div>
    <p class="scan-step">${steps[0]}</p><div class="scan-bar"><div></div></div></div>`).hide().slideDown(250);
    $box.find(".scan-bar div").animate({width:"90%"},steps.length*1600);
    let i=0;const t=setInterval(()=>{i=(i+1)%steps.length;$box.find(".scan-step").fadeOut(150,function(){$(this).text(steps[i]).fadeIn(150)})},1400);
    return ()=>{clearInterval(t);$box.find(".scan-bar div").stop().animate({width:"100%"},200)};
}
function setBusy($btn,on){busy=on;$btn.prop("disabled",on).toggleClass("loading",on)}
function show($box,title,message){
    $box.stop(true,true).html(`<h2>${esc(title)}</h2><p>${esc(message)}</p>`).hide().slideDown(250);
    $("html,body").animate({scrollTop:$box.offset().top-100},500);
}
function animateIn($box){
    $box.find(".confidence-bar div").each(function(){$(this).css("width",0).animate({width:$(this).data("w")+"%"},1100)});
    $box.find(".count-up").each(function(){const $n=$(this),to=+$n.data("n");$({v:0}).animate({v:to},{duration:900,step:v=>$n.text(Math.round(v)),complete:()=>$n.text(to)})});
    $box.find(".source-card,.reason").each((i,el)=>$(el).css({opacity:0,top:12}).delay(250+i*90).animate({opacity:1,top:0},350));
}

/* ---------- news check ---------- */
function sources(title,list,collapsed){
    if(!list?.length)return"";
    const cards=list.map(s=>`<div class="source-card"><div class="sc-head"><h4>${esc(s.source||"Unknown Source")}</h4>
    <span class="badges">${s.fact_check?'<span class="badge fc">Fact-check</span>':""}<span class="badge" title="Publisher credibility">${"★".repeat(Math.max(1,Math.min(5,s.source_score||1)))}</span></span></div>
    <p class="source-title">${esc(s.title||"No title available")}</p>
    <div class="sc-foot"><a href="${safeLink(s.link)}" target="_blank" rel="noopener">Read Source →</a><small>${esc((s.published||"").replace(/ \d\d:\d\d:\d\d.*$/,""))}</small></div></div>`).join("");
    return`<div class="sources-section"><h3 class="${collapsed?"toggle":""}">${title} <small>(${list.length})</small>${collapsed?' <span class="caret">▾</span>':""}</h3><div class="sources-list"${collapsed?' style="display:none"':""}>${cards}</div></div>`;
}

function analyze(){
    const content=$.trim($text.val());
    if(busy)return;
    if(!content){shake($text);return toast("Please enter a news article or claim first.","error")}
    setBusy($("#checkButton"),true);
    const done=loader($result,["Running the language model…","Searching Google News…","Checking fact-checkers…","Classifying evidence…","Weighing source credibility…"]);
    $("html,body").animate({scrollTop:$result.offset().top-120},500);
    $.ajax({url:"/analyze",method:"POST",contentType:"application/json",data:JSON.stringify({text:content}),timeout:90000})
    .done(d=>{done();setTimeout(()=>{render(d,content);saveHistory(content,d.result)},250)})
    .fail(x=>{done();show($result,"Analysis Error",x.responseJSON?.message||"Unable to connect to the TruthLens server.")})
    .always(()=>setBusy($("#checkButton"),false));
}

function render(d,content){
    last={content,d};
    const v=(d.result||"Unknown").toLowerCase(),status=v.includes("misinformation")?"danger":v.includes("reliable")?"safe":"neutral";
    const sup=d.supporting_count??d.supporting_sources?.length??0,con=d.contradicting_count??d.contradicting_sources?.length??0,tot=sup+con;
    const ml=d.ml_label?`<span class="ml-chip ${d.ml_label==="Fake"?"danger":"safe"}">Model: ${esc(d.ml_label)}</span>`:"";
    $result.stop(true,true).html(`<div class="url-result">
    <div class="url-verdict ${status}"><span>${esc(d.result)}</span><small>${esc(d.evidence_strength||"Unknown")} Evidence</small></div>
    <div class="confidence"><div class="confidence-head"><strong>AI Confidence ${ml}</strong><strong>${d.confidence||0}%</strong></div>
    <div class="confidence-bar"><div data-w="${d.confidence||0}"></div></div></div>
    ${tot?`<div class="meter"><div class="meter-head"><span>Supporting <b class="count-up" data-n="${sup}">0</b></span><span>Contradicting <b class="count-up" data-n="${con}">0</b></span></div>
    <div class="meter-bar"><div class="m-sup" style="width:${sup/tot*100}%"></div><div class="m-con" style="width:${con/tot*100}%"></div></div></div>`:""}
    <div class="analysis-details">
        <p><strong>Evidence:</strong> ${esc(d.evidence_strength||"Unknown")}</p>
        <p><strong>Supporting:</strong> <span class="count-up" data-n="${sup}">0</span></p>
        <p><strong>Contradicting:</strong> <span class="count-up" data-n="${con}">0</span></p>
        <p><strong>Fact-checks found:</strong> <span class="count-up" data-n="${d.fact_checks||0}">0</span></p>
        <p><strong>Credible Sources:</strong> <span class="count-up" data-n="${d.credible_sources||0}">0</span></p>
        <p><strong>Independent Sources:</strong> <span class="count-up" data-n="${d.independent_sources||0}">0</span></p>
    </div>
    <div class="result-message"><p>${esc(d.message||"")}</p></div>
    ${d.reasons?.length?`<ul class="reasons">${d.reasons.map(r=>`<li class="reason">${esc(r)}</li>`).join("")}</ul>`:""}
    <div class="result-actions"><button type="button" class="ghost" id="copyReport">Copy report</button><button type="button" class="ghost" id="downloadReport">Download .txt</button><button type="button" class="ghost" id="checkAnother">Check another</button></div>
    ${sources("Supporting Sources",d.supporting_sources)}
    ${sources("Contradicting Sources",d.contradicting_sources)}
    ${sources("Other Relevant Sources",d.other_sources,true)}
    </div>`).hide().fadeIn(350);
    animateIn($result);
}

function report(){
    if(!last)return"";const d=last.d,list=(t,l)=>l?.length?`\n${t}:\n`+l.map(s=>`- ${s.source}: ${s.title}\n  ${s.link}`).join("\n"):"";
    return`TruthLens report — ${new Date().toLocaleString()}\n\nClaim: ${last.content}\n\nVerdict: ${d.result} (${d.evidence_strength} evidence)\nModel: ${d.ml_label||"-"} (${d.confidence}% confidence)\n${d.message}\n`
    +(d.reasons||[]).map(r=>`• ${r}`).join("\n")+"\n"+list("Supporting sources",d.supporting_sources)+list("Contradicting sources",d.contradicting_sources);
}
$result.on("click","#copyReport",()=>navigator.clipboard?.writeText(report()).then(()=>toast("Report copied","ok"),()=>toast("Copy not allowed here","error")))
.on("click","#downloadReport",()=>{const a=$("<a>",{href:URL.createObjectURL(new Blob([report()],{type:"text/plain"})),download:"truthlens-report.txt"})[0];a.click();URL.revokeObjectURL(a.href)})
.on("click","#checkAnother",deleteNews)
.on("click","h3.toggle",function(){$(this).find(".caret").toggleClass("open");$(this).next(".sources-list").slideToggle(300)});

function deleteNews(){
    $text.val("").trigger("input");$result.slideUp(250,()=>$result.empty());last=null;
    $("html,body").animate({scrollTop:$("#checker").offset().top-80},400,()=>$text.trigger("focus"));
}

$("#checkButton").on("click",analyze);
$("#deleteButton").on("click",deleteNews);
$(".chip").on("click",function(){$text.val($(this).data("text")).trigger("input");$text.css("opacity",.4).animate({opacity:1},400)});
$text.on("input",function(){
    const n=this.value.length;$count.text(n);
    $("#charMeter").stop().animate({width:Math.min(100,n/30*100)+"%"},150).toggleClass("ok",n>=30);
    $("#charHint").text(n>=30?"Good length for analysis":"30+ characters recommended");
}).on("keydown",e=>{
    if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();analyze()}
    if(e.key==="Delete"&&e.ctrlKey&&$text.val())deleteNews(); // Ctrl+Delete clears; plain Delete edits normally
});

/* ---------- recent checks (stored only in this browser) ---------- */
const H="truthlens-history",getH=()=>{try{return JSON.parse(localStorage.getItem(H))||[]}catch(e){return[]}};
function saveHistory(text,verdict){try{localStorage.setItem(H,JSON.stringify([{text,verdict},...getH().filter(h=>h.text!==text)].slice(0,6)))}catch(e){}renderHistory()}
function renderHistory(){
    const h=getH();$("#history").prop("hidden",!h.length);
    $("#historyList").html(h.map((x,i)=>{const v=x.verdict.toLowerCase(),c=v.includes("misinformation")?"danger":v.includes("reliable")?"safe":"neutral";
        return`<li data-i="${i}"><span class="dot ${c}"></span><span class="h-text">${esc(x.text)}</span><small>${esc(x.verdict)}</small></li>`}).join(""));
}
$("#historyList").on("click","li",function(){$text.val(getH()[$(this).data("i")].text).trigger("input");$("html,body").animate({scrollTop:$("#checker").offset().top-80},400)});
$("#clearHistory").on("click",()=>{try{localStorage.removeItem(H)}catch(e){}$("#history").slideUp(250,renderHistory)});
renderHistory();

/* ---------- URL check ---------- */
function checkURL(){
    const content=$.trim($url.val());
    if(busy)return;
    if(!content){shake($url);return toast("Please enter a URL first.","error")}
    setBusy($("#urlButton"),true);
    const done=loader($urlResult,["Extracting URL features…","Running the phishing model…","Checking security signals…"]);
    $.ajax({url:"/check-url",method:"POST",contentType:"application/json",data:JSON.stringify({url:content}),timeout:30000})
    .done(d=>{done();setTimeout(()=>renderURL(d),250)})
    .fail(x=>{done();show($urlResult,"URL Analysis Error",x.responseJSON?.message||"Unable to connect to the TruthLens server.")})
    .always(()=>setBusy($("#urlButton"),false));
}

function renderURL(d){
    const verdict=d.result||"Unknown",confidence=d.confidence||0,risk=d.risk??0;
    const status=/phishing|unsafe|malicious/i.test(verdict)?"danger":/legit|safe/i.test(verdict)?"safe":"neutral";
    $urlResult.stop(true,true).html(`<div class="url-result">
    <div class="url-verdict ${status}"><span>${esc(verdict)}</span><small>${esc(d.level||"Unknown")} Risk</small></div>
    ${d.domain?`<p class="url-domain">Real domain: <b>${esc(d.domain)}</b> · Model phishing score: ${d.ml_probability??"-"}%</p>`:""}
    <div class="confidence"><div class="confidence-head"><strong>Detection Confidence</strong><strong>${confidence}%</strong></div>
    <div class="confidence-bar"><div data-w="${confidence}"></div></div></div>
    <div class="confidence"><div class="confidence-head"><strong>Risk Score</strong><strong><span class="count-up" data-n="${risk}">0</span> / 100</strong></div>
    <div class="confidence-bar risk"><div data-w="${risk}"></div></div></div>
    <div class="sources-section"><h3>Warning signs</h3><div class="sources-list">
    ${(d.reasons||[]).length?d.reasons.map(r=>`<div class="source-card warn"><p class="source-title">${esc(r)}</p></div>`).join(""):'<div class="source-card"><p class="source-title">No suspicious URL patterns found.</p></div>'}
    </div></div>
    ${(d.good||[]).length?`<div class="sources-section"><h3>Trust signals</h3><div class="sources-list">${d.good.map(g=>`<div class="source-card ok"><p class="source-title">${esc(g)}</p></div>`).join("")}</div></div>`:""}
    </div>`).hide().fadeIn(350);
    animateIn($urlResult);
}

function deleteURL(){$url.val("");$urlResult.slideUp(250,()=>$urlResult.empty());$url.trigger("focus")}
$("#urlButton").on("click",checkURL);
$("#urlDeleteButton").on("click",deleteURL);
$url.on("keydown",e=>{if(e.key==="Enter"){e.preventDefault();checkURL()}});
});
