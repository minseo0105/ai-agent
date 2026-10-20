import type { BankState } from "./Banking";

export type Policy = { frequency: "weekly" | "monthly"; amount: number; pay_day: number; rate_bps: number; cap: number; rollover: boolean };
export type Child = { id: string; profile: {name: string; grade: number; avatar: string; theme: string}; policy: Policy; status: string };
export type Cycle = {id: string; start: string; end: string; eligible: number; interest: number; ended: boolean; settled: number; policy: Policy};
export type RewardItem = {payment_mode?:string;cycle_id:string;start:string;end:string;reward_type:"allowance_bonus"|"savings_interest";base:number;amount:number;rate_bps:number;cap:number|null;destination:"wallet"|"vault";status:"estimated"|"awaiting_approval"|"paid";paid_amount:number;paid_at:string|null;transaction_id:string|null};
export type SavingsBook = {request_key:string;id:string;name:string;target:number;icon:string;color:string;nickname:string;balance:number;interest?:number;history:{id:string;kind:string;created:string;amount:number}[]};
export type PayoutChoice = {payout:string;amount:number;available:number;choice:{choice:string;amount:number}|null};
export type State = {books?:SavingsBook[];payout_choices?:PayoutChoice[];payment_rule?:{current:string;scheduled:{effective:string;mode:string}[]};education?:{start:string;end:string;received:number;spent:number;saved:number;opening:number;interest_received:number;withdrawn:number;other_in:number;other_out:number;remaining:number;parent_balance:number};rewards?:{items:RewardItem[];estimates:Record<string,number>;expected_total:number;destination:string};wallet: number; vault: number; next_payday: string; cycles: Cycle[]; xp: number; stage: number; badges: string[]; quests: string[]; banking:BankState; report: {paid:number;spent:number;interest:number;categories:Record<string,number>;record_days:number;savings_rate:number|null}; transactions: {id: string; request_key:string; kind: string; wallet: number; vault: number; note: string; category: string; created: string}[]; goals: {id: string; name: string; amount: number}[]};
export type ChildTransaction = {book_id?:string;kind:"expense"|"deposit"|"withdraw";amount:number;note?:string;category?:string;merchant?:string};
export type MoneyApi = (path:string,body?:unknown,auth?:string,method?:string)=>Promise<unknown>;
export type RunAction = (action:()=>Promise<void>)=>Promise<void>;
