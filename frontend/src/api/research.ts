import {request,post,patch} from './client';
export const researchApi={
 runs:()=>request('/runs'),
 notes:()=>request('/notes'),
 createRun:(data:any)=>post('/runs',data),
 retryRun:(id:number)=>post('/runs/'+id+'/retry',{}),
 createNote:(data:any)=>post('/notes',data),
 approve:(id:number,data:any)=>patch('/notes/'+id+'/approval',data),
};
