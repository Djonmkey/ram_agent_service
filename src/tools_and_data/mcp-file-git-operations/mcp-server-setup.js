// mcp-file-git-server.js
// MCP Server for File Operations and Git Commands

const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { StdioServerTransport } = require('@modelcontextprotocol/sdk/server/stdio.js');
const fs = require('fs').promises;
const path = require('path');
const { exec } = require('child_process');
const { promisify } = require('util');

const execAsync = promisify(exec);

// Configuration
const CONFIG = {
  rootPath: '/Users/david/Documents/projects/product-sandbox/solutions/',
  aiDocsFolder: 'ai_docs',
  defaultFileName: 'problem_statement.md'
};

// Initialize MCP Server
const server = new Server(
  {
    name: 'file-git-operations',
    version: '1.0.0',
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// Helper function to ensure directory exists
async function ensureDirectory(dirPath) {
  try {
    await fs.mkdir(dirPath, { recursive: true });
  } catch (error) {
    console.error(`Error creating directory: ${error.message}`);
    throw error;
  }
}

// Helper function to create slug from problem title
function createSlug(title) {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .trim();
}

// Tool: Write Problem Statement
server.setRequestHandler('tools/list', async () => ({
  tools: [
    {
      name: 'write_problem_statement',
      description: 'Write the problem statement to a markdown file in the specified project structure',
      inputSchema: {
        type: 'object',
        properties: {
          problemTitle: {
            type: 'string',
            description: 'The title of the problem (will be used to create the folder slug)'
          },
          content: {
            type: 'string',
            description: 'The markdown content of the problem statement'
          },
          customSlug: {
            type: 'string',
            description: 'Optional: Override the auto-generated slug with a custom one'
          }
        },
        required: ['problemTitle', 'content']
      }
    },
    {
      name: 'git_add_commit_push',
      description: 'Add, commit, and push the problem statement file to git',
      inputSchema: {
        type: 'object',
        properties: {
          filePath: {
            type: 'string',
            description: 'The full path to the file to commit'
          },
          commitMessage: {
            type: 'string',
            description: 'The commit message'
          },
          branch: {
            type: 'string',
            description: 'Optional: The branch to push to (defaults to current branch)'
          }
        },
        required: ['filePath', 'commitMessage']
      }
    },
    {
      name: 'check_file_exists',
      description: 'Check if a problem statement file already exists for a given slug',
      inputSchema: {
        type: 'object',
        properties: {
          slug: {
            type: 'string',
            description: 'The project slug to check'
          }
        },
        required: ['slug']
      }
    }
  ]
}));

// Tool Handler: Write Problem Statement
server.setRequestHandler('tools/call', async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'write_problem_statement': {
        const { problemTitle, content, customSlug } = args;
        
        // Generate slug
        const slug = customSlug || createSlug(problemTitle);
        
        // Create full paths
        const projectPath = path.join(CONFIG.rootPath, slug);
        const aiDocsPath = path.join(projectPath, CONFIG.aiDocsFolder);
        const filePath = path.join(aiDocsPath, CONFIG.defaultFileName);
        
        // Ensure directories exist
        await ensureDirectory(aiDocsPath);
        
        // Write the file
        await fs.writeFile(filePath, content, 'utf8');
        
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({
                success: true,
                message: 'Problem statement written successfully',
                filePath: filePath,
                projectPath: projectPath,
                slug: slug
              }, null, 2)
            }
          ]
        };
      }
      
      case 'git_add_commit_push': {
        const { filePath, commitMessage, branch } = args;
        
        // Get the directory of the file
        const fileDir = path.dirname(filePath);
        
        // Check if it's a git repository
        try {
          await execAsync('git status', { cwd: fileDir });
        } catch (error) {
          // If not a git repo, initialize it
          await execAsync('git init', { cwd: fileDir });
        }
        
        // Add the file
        await execAsync(`git add "${path.basename(filePath)}"`, { cwd: fileDir });
        
        // Commit
        await execAsync(`git commit -m "${commitMessage}"`, { cwd: fileDir });
        
        // Push (if branch specified)
        let pushResult = '';
        if (branch) {
          try {
            const { stdout } = await execAsync(`git push origin ${branch}`, { cwd: fileDir });
            pushResult = stdout;
          } catch (error) {
            pushResult = `Push failed: ${error.message}. You may need to set up remote or push manually.`;
          }
        } else {
          pushResult = 'Committed locally. Run "git push" manually or specify a branch.';
        }
        
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify({
                success: true,
                message: 'Git operations completed',
                operations: {
                  add: 'Success',
                  commit: 'Success',
                  push: pushResult
                }
              }, null, 2)
            }
          ]
        };
      }
      
      case 'check_file_exists': {
        const { slug } = args;
        const filePath = path.join(CONFIG.rootPath, slug, CONFIG.aiDocsFolder, CONFIG.defaultFileName);
        
        try {
          await fs.access(filePath);
          const content = await fs.readFile(filePath, 'utf8');
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  exists: true,
                  filePath: filePath,
                  preview: content.substring(0, 200) + '...'
                }, null, 2)
              }
            ]
          };
        } catch (error) {
          return {
            content: [
              {
                type: 'text',
                text: JSON.stringify({
                  exists: false,
                  filePath: filePath
                }, null, 2)
              }
            ]
          };
        }
      }
      
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [
        {
          type: 'text',
          text: JSON.stringify({
            success: false,
            error: error.message
          }, null, 2)
        }
      ]
    };
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('MCP File/Git Operations Server running on stdio');
}

main().catch((error) => {
  console.error('Server error:', error);
  process.exit(1);
});