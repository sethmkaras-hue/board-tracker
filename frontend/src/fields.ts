export const types = ['External IO','Power','Digital','RF','Antenna','Backplane','Other']
export const levels = ['Low','Medium','High','Very High']
export const tools = ['Altium','PADS','Other']
export const checks = ['Not Started','In Progress','Complete']
export const states = ['Not Started','Scheduled','In-Review','Working Action Items','Complete']
export const reviews = ['Functional Overview Review','Detailed Design Review','Schematic Review','Artwork Review','Board Verification (Unit Test)']
export const labels:Record<string,string> = {
  identifier:'Board identifier', active:'Active', schematic_ri_id:'Schematic RI', layout_ri_id:'Layout RI', board_ri_ids:'Board RIs',
  program_ids:'Programs', board_type:'Board type', complexity:'Complexity', reuse_level:'Reuse level', maturity:'Maturity level',
  schematic_tool:'Schematic tool', layout_tool:'Layout tool', components_status:'Components checking', aras_board_url:'ARAS board top level',
  aras_export_url:'ARAS export classification', overview_url:'Functional overview', notes:'Notes', manager_ids:'Program managers',
  deputy_ids:'Deputy program managers', epm_id:'EPM', name:'Name', quantity:'Quantity per system', url:'Parent system ARAS URL',
  state:'State', date:'Review date', deleted_at:'Deleted', created_at:'Created', updated_at:'Last modified',
}
