import {request,post,patch} from './client';
export const sourceApi={
 studies:()=>request('/studies'),
 levels:()=>request('/levels'),
 readings:()=>request('/readings'),
 create:(data:any)=>post('/studies',data),
 editLevel:(id:number,data:any)=>patch('/levels/'+id,data),
 editReading:(id:number,data:any)=>patch('/readings/'+id,data),
 instruments:()=>request('/instruments'),
 createInstrument:(data:any)=>post('/instruments',data),
 calibrations:(id:number)=>request('/instruments/'+id+'/calibrations'),
 publishCalibration:(id:number,data:any)=>post('/instruments/'+id+'/calibrations',data),
 bind:(id:number,data:any)=>patch('/studies/'+id+'/instrument',data),
 current:(id:number)=>request('/studies/'+id+'/current'),
 trace:(id:number)=>request('/studies/'+id+'/trace'),
};
