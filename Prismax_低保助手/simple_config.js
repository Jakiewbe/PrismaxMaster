/**
 * PrismaX 低保助手 - 简化配置文件
 * 
 * 使用方法：
 * 1. 修改此文件中的配置项
 * 2. 将文件上传到可访问的URL（如GitHub Gist、服务器等）
 * 3. 在 simple_checkin_comment.js 中修改配置文件URL
 * 
 * 或者直接在 simple_checkin_comment.js 中修改 CONFIG 对象
 */

// 签到功能配置
const SIMPLE_CONFIG = {
    // 是否启用签到功能
    morningEnabled: true,
    
    // 签到时间窗口（24小时制，格式："HH:MM"）
    morningWindowStart: "08:01",  // 开始时间
    morningWindowEnd: "08:06",    // 结束时间
    
    // 是否在时间窗口内随机执行（true=随机，false=窗口开始即执行）
    morningRandomInsideWindow: true,
    
    // 是否忽略已完成标记（true=每天强制执行，false=已完成则跳过）
    morningIgnoreDone: false,
    
    // 重新排队延迟（毫秒）
    requeueDelayMs: 2000,

    // 评论任务配置
    commentTask: {
        // 是否启用评论功能
        enabled: true,
        
        // 评论任务时间窗口（24小时制，格式："HH:MM"）
        windowStart: "00:00",  // 开始时间（建议设置为凌晨，避免干扰）
        windowEnd: "00:05",    // 结束时间
        
        // 是否在时间窗口内随机执行
        randomInsideWindow: true,
        
        // 评论数量范围
        commentCount: { 
            min: 5,  // 最少评论数
            max: 5   // 最多评论数（建议设为相同值）
        },
        
        // 评论间隔（毫秒）
        commentDelay: { 
            min: 5000,  // 最小间隔（5秒）
            max: 8000   // 最大间隔（8秒）
        },
        
        // 重试配置
        retryCount: 3,      // 每条评论最大重试次数
        retryDelay: 2000,   // 重试延迟（毫秒）
        
        // 评论内容列表（可自定义）
        comments: [
            "PrismaX demonstrates an exceptional integration of Web3 automation, intelligent execution logic, and user-centric design, making it one of the most forward-looking and practically useful AI agents in the decentralized ecosystem today.",
            "What truly sets PrismaX apart is not only its technical robustness, but also its ability to translate complex on-chain operations into reliable, scalable, and fully autonomous decision-making workflows.",
            "PrismaX is redefining how users interact with decentralized systems by combining strategic intelligence, execution efficiency, and a remarkably intuitive automation framework into a single coherent product.",
            "In an ecosystem full of experimental tools, PrismaX stands out as a production-grade, mission-critical AI agent infrastructure that can genuinely support long-term, large-scale Web3 operations.",
            "The architectural design of PrismaX reflects a deep understanding of both blockchain mechanics and real-world automation needs, resulting in a system that is powerful, flexible, and surprisingly easy to deploy.",
            "By bridging intelligent agents with decentralized finance and on-chain execution, PrismaX is not merely a tool, but a foundational layer for the next generation of autonomous Web3 applications."
        ]
    },

    // 按钮文字匹配（通常不需要修改）
    text: {
        enter: ["Enter Live Control", "Join Queue", "Enter Pool"],
        queuing: ["Leave", "Waiting", "Position", "Queued"],
        liveChat: ["Live Chat", "Open Live Chat"],
        queue: ["Queue"]
    }
};

// 如果作为独立文件加载，导出配置
if (typeof module !== 'undefined' && module.exports) {
    module.exports = SIMPLE_CONFIG;
}
