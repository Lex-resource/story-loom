/**
 * 后端 400 的 detail 约定:多条校验错误拼成多行字符串,每行以「·」开头
 * (见 services/system_configs_service._validate_pipeline_update 与
 * routers/system_configs 的 runtime-tunables PUT)。拆成逐条展示。
 */
export function asErrorList(message) {
  return String(message || '')
    .split('\n')
    .map((line) => line.replace(/^·\s*/, '').trim())
    .filter(Boolean);
}
