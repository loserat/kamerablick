(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.TVRemote=factory()})(globalThis,function(){
  const keys=new Set(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Enter','Escape']);
  class Receiver{
    constructor(client){this.client=client;this.reset()}
    reset(){this.boot=null;this.cursor=null}
    request(){return {client:this.client,boot:this.boot,cursor:this.cursor}}
    accept(data){
      if(typeof data.boot!=='string'||!Number.isSafeInteger(data.cursor)||data.cursor<0)throw Error('Ungültige Tastenantwort');
      const previous=this.cursor;const same=this.boot===data.boot;
      this.boot=data.boot;this.cursor=data.cursor;
      if(!same||previous===null||data.waiting)return [];
      let seen=previous;
      return (Array.isArray(data.events)?data.events:[]).filter(e=>{
        if(!Number.isSafeInteger(e.id)||e.id<=seen||e.id>data.cursor||!keys.has(e.key))return false;
        seen=e.id;return true;
      }).map(e=>e.key);
    }
  }
  return {Receiver};
});
