export type KidIconName="home"|"account"|"savings"|"arrow"|"back"|"plus"|"edit"|"leaf"|"gift"|"down"|"up"|"check"|"lock"|"star"|"help";
export default function KidIcon({name,className=""}:{name:KidIconName;className?:string}) {
  const paths:Record<KidIconName,React.ReactNode>={
    home:<><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/><path d="M9 21h6"/></>,
    account:<><rect x="3" y="4" width="18" height="16" rx="4"/><path d="M7 9h6m-6 5h10m0-5h.1"/></>,
    savings:<><path d="M18 8c3 2 3 6 1 9v3h-3v-2H8v2H5v-4c-3-3-2-7 2-9l1-4 4 3h4l3-2v4Z"/><path d="M10 9h4m4 3h.1M3 10l-1-1"/></>,
    arrow:<path d="M4 12h15m-5-5 5 5-5 5"/>,back:<path d="m14 5-7 7 7 7"/>,plus:<path d="M12 5v14M5 12h14"/>,
    edit:<><path d="m15 4 5 5-11 11-6 1 1-6Z"/><path d="m12 7 5 5"/></>,
    leaf:<><path d="M5 20C2 9 9 3 21 3c0 12-6 19-16 17Z"/><path d="m4 21 10-11"/></>,
    gift:<><rect x="3" y="8" width="18" height="4" rx="1"/><path d="M5 12v9h14v-9M12 8v13m0-13C4 8 6 1 9 4l3 4Zm0 0c8 0 6-7 3-4l-3 4Z"/></>,
    down:<path d="M12 4v16m-6-6 6 6 6-6"/>,up:<path d="M12 20V4m-6 6 6-6 6 6"/>,
    check:<path d="m5 12 5 5L20 6"/>,lock:<><rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/></>,
    star:<path d="m12 3 3 6 7 1-5 5 1 7-6-4-6 4 1-7-5-5 7-1Z"/>,
    help:<><circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5m0 3h.1"/></>,
  };
  return <svg className={`mk-icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}
