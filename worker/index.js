// worker/index.js
// Cloudflare Workers - Multi-Task GitHub Actions Trigger

// 任务映射表：将 Cron 表达式与 {id: 文件名, input: Actions参数} 关联起来
// Cron 表达式已精确转换为 UTC 时间
const CRON_TO_WORKFLOW = {
    // =========================================================================
    // 1. cleaner.yml
    "0 19 * * 7": { 
        id: "cleaner.yml", 
        description: "Weekly Cleanup (cleaner.yml)",
        input: {} // 清理任务无需额外参数
    },
    // =========================================================================
    // 2. scheduler.yml - TASK_1
    "0 22 * * *": { 
        id: "scheduler.yml", 
        description: "Daily Schedule (TASK_1)",
        input: { task_to_run: "TASK_1" } // 传入任务ID
    },
    // =========================================================================
    // 3. scheduler.yml - TASK_2
    "10 2,6,10,14,18,22 * * *": { 
        id: "scheduler.yml", 
        description: "4-Hourly Schedule (TASK_2)",
        input: { task_to_run: "TASK_2" } // 传入任务ID
    },
    // =========================================================================
    // 4. scheduler.yml - TASK_3
    "15,20,25,30,35,40,45,50,55 22-23,0-15 * * *": {
        id: "scheduler.yml", 
        description: "High-Frequency Schedule (TASK_3)",
        input: { task_to_run: "TASK_3" } // 传入任务ID
    }
};


export default {
    async scheduled(event, env, ctx) {
        const { CLOUDFLARE_WORKER, GITHUB_OWNER, GITHUB_REPO, TARGET_BRANCH } = env;
        
        // 1. 根据触发的 Cron 表达式 (event.cron) 查找对应的工作流配置
        const taskConfig = CRON_TO_WORKFLOW[event.cron];

        if (!taskConfig) {
            console.error(`ERROR: No workflow configured for Cron expression: ${event.cron}`);
            return;
        }
        
        const WORKFLOW_ID = taskConfig.id;
        const taskDescription = taskConfig.description;

        if (!CLOUDFLARE_WORKER) {
            console.error("FATAL ERROR: CLOUDFLARE_WORKER is missing or invalid in Worker environment.");
            throw new Error("Worker failed: Missing GitHub PAT Secret.");
        }

        // 2. 构造 API URL 和请求体
        const apiUrl = `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/workflows/${WORKFLOW_ID}/dispatches`;

        const requestBody = JSON.stringify({
            ref: TARGET_BRANCH || "main", 
            inputs: taskConfig.input // 动态传递任务参数
        });

        const headers = {
            'Accept': 'application/vnd.github.v3+json',
            'Authorization': `token ${CLOUDFLARE_WORKER}`,
            'User-Agent': `Cloudflare-Worker-${taskDescription}`,
            'Content-Type': 'application/json',
        };

        // 3. 执行 POST 请求
        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: headers,
                body: requestBody,
            });

            if (response.status === 204) {
                console.log(`SUCCESS: ${taskDescription} triggered by cron: ${event.cron}`);
            } else {
                const errorText = await response.text();
                console.error(`FAILURE: Workflow trigger failed for ${WORKFLOW_ID} (Status: ${response.status}): ${errorText}`);
                throw new Error(`GitHub API Error for ${WORKFLOW_ID}: ${response.status}`);
            }
        } catch (error) {
            console.error('Fetch error:', error);
            throw error;
        }
    },
    // 添加这个函数来处理网页访问，防止 Error 1101
    async fetch(request, env, ctx) {
        return new Response("This Worker is a Cron Scheduler and does not serve web content.", { status: 200 });
    }
};