// 校验 Git 提交说明，基于 Conventional Commits 规范。
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // 允许的提交类型。
    'type-enum': [
      2,
      'always',
      ['feat', 'fix', 'docs', 'style', 'refactor', 'perf', 'test', 'chore', 'revert'],
    ],
    // 简短说明最多 50 个字符。
    'subject-max-length': [2, 'always', 50],
    // 正文每行最多 72 个字符。
    'body-max-line-length': [2, 'always', 72],
  },
};
