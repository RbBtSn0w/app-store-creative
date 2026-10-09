export function specimen() {
  return { binding: {workspace:'/product/work', objects:'/product/work/objects', releases:'/product/releases', publications:'/product/publications'},
    roots: {workspaceRoot:{configured:'work', source:'project', resolved:'/product/work'},
      objectRoot:{configured:null, source:'derived', resolved:'/product/work/objects'},
      releaseRoot:{configured:null, source:'default', resolved:'/product/releases'},
      publicationRoot:{configured:null, source:'default', resolved:'/product/publications'}},
    roots_changed:true, requires_relocation:false, project_identity_conflict:false, configuration_path:'/product/creative.config.json', writes_performed:false };
}
