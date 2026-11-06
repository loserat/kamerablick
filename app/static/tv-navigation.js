/* Geometry-based focus navigation, shared with the small Node test. */
(function(root){
  function spatial(items,current,key){
    const origin=items.find(item=>item.id===current);
    if(!origin)return items[0]?.id||null;
    const horizontal=key==='ArrowLeft'||key==='ArrowRight';
    const sign=key==='ArrowRight'||key==='ArrowDown'?1:-1;
    let result=current,best=Infinity;
    for(const item of items){
      const primary=(horizontal?item.x-origin.x:item.y-origin.y)*sign;
      if(primary<=2)continue;
      const cross=Math.abs(horizontal?item.y-origin.y:item.x-origin.x);
      const score=primary+cross*3;
      if(score<best){best=score;result=item.id}
    }
    return result;
  }
  function next(items,current,key){
    const origin=items.find(item=>item.id===current);
    if(origin?.group==='cameras'){
      const cameras=items.filter(item=>item.group==='cameras');
      if(key==='ArrowLeft'||key==='ArrowRight')
        return spatial(cameras.filter(item=>Math.abs(item.y-origin.y)<3),current,key);
      const sign=key==='ArrowDown'?1:-1;
      const candidates=cameras.filter(item=>(item.y-origin.y)*sign>3);
      if(candidates.length){
        const distance=Math.min(...candidates.map(item=>(item.y-origin.y)*sign));
        const row=candidates.filter(item=>Math.abs((item.y-origin.y)*sign-distance)<3);
        return row.reduce((best,item)=>Math.abs(item.x-origin.x)<Math.abs(best.x-origin.x)?item:best).id;
      }
      return spatial(items.filter(item=>item.id===current||item.group!=='cameras'),current,key);
    }
    return spatial(items,current,key);
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={next};
  else root.TVNavigation={next};
})(typeof window==='undefined'?{}:window);
