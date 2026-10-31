/* Geometry-based focus navigation, shared with the small Node test. */
(function(root){
  function next(items,current,key){
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
  if(typeof module!=='undefined'&&module.exports)module.exports={next};
  else root.TVNavigation={next};
})(typeof window==='undefined'?{}:window);
