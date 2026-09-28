/* AquaIntel lightweight local chart renderer. No external network dependency. */
(function () {
  class Chart {
    constructor(canvas, config) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.config = config || {};
      this.data = this.config.data || {labels: [], datasets: []};
      this.options = this.config.options || {};
      this.resize = this.resize.bind(this);
      window.addEventListener('resize', this.resize);
      this.update();
    }
    update() { this.draw(); }
    destroy() { window.removeEventListener('resize', this.resize); }
    resize() { this.draw(); }
    draw() {
      const c = this.canvas, ctx = this.ctx;
      if (!c || !ctx) return;
      const dpr = window.devicePixelRatio || 1;
      const rect = c.getBoundingClientRect();
      const w = Math.max(320, Math.min(rect.width || c.clientWidth || 640, 1200));
      const h = 320;
      c.width = Math.round(w * dpr); c.height = Math.round(h * dpr);
      ctx.setTransform(dpr,0,0,dpr,0,0);
      ctx.clearRect(0,0,w,h);
      if (this.config.type === 'doughnut') return this.drawDoughnut(w,h);
      return this.drawLine(w,h);
    }
    drawLine(w,h) {
      const ctx=this.ctx, labels=this.data.labels||[], ds=this.data.datasets?.[0]||{}, vals=(ds.data||[]).map(Number).filter(Number.isFinite);
      if (!vals.length) { ctx.fillStyle='#7a92ab'; ctx.font='14px Segoe UI,Arial'; ctx.fillText('No chart data available.',20,30); return; }
      const pad={l:48,r:18,t:18,b:34}, pw=w-pad.l-pad.r, ph=h-pad.t-pad.b;
      const min=Math.min(...vals), max=Math.max(...vals), span=max-min || 1;
      ctx.strokeStyle='#29445f'; ctx.lineWidth=1; ctx.font='11px Segoe UI,Arial'; ctx.fillStyle='#7a92ab';
      for(let i=0;i<5;i++){const y=pad.t+ph*i/4;ctx.beginPath();ctx.moveTo(pad.l,y);ctx.lineTo(w-pad.r,y);ctx.stroke();const v=max-span*i/4;ctx.fillText(Number(v.toFixed(2)).toString(),4,y+4);}
      ctx.strokeStyle='#4fc3f7'; ctx.lineWidth=2; ctx.beginPath();
      vals.forEach((v,i)=>{const x=pad.l+(vals.length===1?pw/2:pw*i/(vals.length-1));const y=pad.t+ph*(max-v)/span;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();
      ctx.fillStyle='#4fc3f7'; vals.forEach((v,i)=>{const x=pad.l+(vals.length===1?pw/2:pw*i/(vals.length-1));const y=pad.t+ph*(max-v)/span;ctx.beginPath();ctx.arc(x,y,3,0,Math.PI*2);ctx.fill();});
      ctx.fillStyle='#7a92ab'; const step=Math.max(1,Math.ceil(labels.length/6)); labels.forEach((lab,i)=>{if(i%step!==0)return;const x=pad.l+(labels.length===1?pw/2:pw*i/(labels.length-1));ctx.fillText(String(lab),Math.max(pad.l,x-24),h-10);});
    }
    drawDoughnut(w,h) {
      const ctx=this.ctx, ds=this.data.datasets?.[0]||{}, vals=(ds.data||[]).map(Number), total=vals.reduce((a,b)=>a+(Number.isFinite(b)?b:0),0);
      if(total<=0){ctx.fillStyle='#7a92ab';ctx.font='14px Segoe UI,Arial';ctx.fillText('No assets available.',20,30);return;}
      const cx=w*0.35,cy=h*0.5,r=Math.min(w*0.23,h*0.35), colors=['#27ae60','#e67e22','#4fc3f7','#e74c3c'];let a=-Math.PI/2;
      vals.forEach((v,i)=>{const b=a+(v/total)*Math.PI*2;ctx.beginPath();ctx.moveTo(cx,cy);ctx.arc(cx,cy,r,a,b);ctx.closePath();ctx.fillStyle=colors[i%colors.length];ctx.fill();a=b;});
      ctx.beginPath();ctx.arc(cx,cy,r*0.58,0,Math.PI*2);ctx.fillStyle=getComputedStyle(this.canvas).backgroundColor||'#12233b';ctx.fill();
      ctx.font='13px Segoe UI,Arial';(this.data.labels||[]).forEach((lab,i)=>{const y=cy-24+i*24;ctx.fillStyle=colors[i%colors.length];ctx.fillRect(w*0.68,y-9,12,12);ctx.fillStyle='#e0e6ed';ctx.fillText(`${lab}: ${vals[i]||0}`,w*0.71,y+2);});
    }
  }
  window.Chart=Chart;
})();
