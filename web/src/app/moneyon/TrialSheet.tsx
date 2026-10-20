"use client";
import { useEffect, useRef, type ReactNode } from "react";

export default function TrialSheet({title,onClose,children}:{title:string;onClose:()=>void;children:ReactNode}) {
  const dialog=useRef<HTMLDialogElement>(null);
  useEffect(()=>{
    const node=dialog.current!, previous=document.activeElement as HTMLElement|null;
    const overflow=document.body.style.overflow;
    node.showModal();document.body.style.overflow="hidden";
    return()=>{node.close();document.body.style.overflow=overflow;previous?.focus();};
  },[]);
  return <dialog ref={dialog} className="mk-sheet" aria-label={title} onCancel={e=>{e.preventDefault();onClose();}}>
    <header className="mk-sheet-header"><h2>{title}</h2><button type="button" className="mk-sheet-close" aria-label="닫기" onClick={onClose}>×</button></header>
    <div className="mk-sheet-body">{children}</div>
  </dialog>;
}
