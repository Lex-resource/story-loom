import WorkflowPromptEditor from '../workflow/WorkflowPromptEditor';

export default function PromptConfigPanel({ category, prompts, api, guard, reloadPrompts }) {
  return (
    <WorkflowPromptEditor
      category={category}
      prompts={prompts}
      onCreate={async (payload) => {
        await guard(() => api.createPrompt(payload), '提示词已创建');
        await reloadPrompts();
      }}
      onUpdate={async (id, payload) => {
        await guard(() => api.updatePrompt(id, payload), '提示词已保存');
        await reloadPrompts();
      }}
      onDelete={async (id) => {
        await guard(() => api.deletePrompt(id), '提示词已删除');
        await reloadPrompts();
      }}
    />
  );
}
