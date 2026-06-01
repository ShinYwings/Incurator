import * as nunjucks from 'nunjucks';
import { App } from 'obsidian';
import { moment } from 'obsidian';

export function sanitizePathSegment(value: unknown): string {
  return String(value ?? "")
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

class PersistExtension implements nunjucks.Extension {
  tags = ['persist'];

  parse(parser: any, nodes: any, lexer: any) {
    const tok = parser.nextToken();
    const args = parser.parseSignature(null, true);
    parser.advanceAfterBlockEnd(tok.value);
    const body = parser.parseUntilBlocks('endpersist');
    parser.advanceAfterBlockEnd();
    return new nodes.CallExtension(this, 'run', args, [body]);
  }

  run(context: any, name: string, body: () => string) {
    let retainedText = '';
    if (context?.ctx?._retained && context.ctx._retained[name]) {
      retainedText = context.ctx._retained[name];
    }
    let bodyText = body();
    if (retainedText) {
      bodyText = bodyText.trimStart();
    }
    return new nunjucks.runtime.SafeString(`%% begin ${name} %%${retainedText}${bodyText}%% end ${name} %%`);
  }

  static hasPersist(text: string): boolean {
    return /%% begin (.+?) %%([\w\W]*?)%% end \1 %%/gi.test(text);
  }

  static prepareTemplateData(data: any, existingContent?: string): any {
    const retained: Record<string, string> = {};
    if (existingContent) {
      const matches = existingContent.matchAll(/%% begin (.+?) %%([\w\W]*?)%% end \1 %%/gi);
      for (const match of matches) {
        retained[match[1]] = match[2];
      }
    }
    return { ...data, _retained: retained };
  }
}

export class TemplateRenderer {
  private env: nunjucks.Environment;
  
  constructor(private app: App) {
    // We don't use file loader because we'll read templates directly from Obsidian Vault
    this.env = new nunjucks.Environment(null, { autoescape: false });
    this.env.addExtension('PersistExtension', new PersistExtension());
    
    // Add custom filters
    this.env.addFilter('format', function(dateStr, formatStr) {
      if (!dateStr) return '';
      return (moment as any)(dateStr).format(formatStr);
    });
    
    this.env.addFilter('replace', function(str: string, search: string|RegExp, replace: string) {
      if (typeof str !== 'string') return str;
      if (search instanceof RegExp) {
        return str.replace(search, replace);
      }
      return str.split(search as string).join(replace);
    });
    
    this.env.addFilter('firstAuthorLast', function(creators: any[]) {
      if (!Array.isArray(creators)) return '';
      return creators.find((creator) => creator?.lastName)?.lastName || '';
    });

    this.env.addFilter('authorLast', function(creators: any[], index = 0) {
      if (!Array.isArray(creators)) return '';
      return creators[index]?.lastName || '';
    });

    this.env.addFilter('joinTags', function(tags: any[], separator = ', ') {
      if (!Array.isArray(tags)) return '';
      return tags
        .map((tag) => typeof tag === 'string' ? tag : tag?.tag)
        .filter(Boolean)
        .join(separator);
    });

    this.env.addFilter('pathSafe', function(value: unknown) {
      return sanitizePathSegment(value);
    });
  }
  
  public async renderTemplate(templatePath: string, data: any, existingContent?: string): Promise<string> {
    const tFile = this.app.metadataCache.getFirstLinkpathDest(templatePath, '');
    if (!tFile) {
      throw new Error(`Template not found at: ${templatePath}`);
    }
    
    const templateText = await this.app.vault.read(tFile);
    const preparedData = PersistExtension.prepareTemplateData(data, existingContent);
    
    return new Promise((resolve, reject) => {
      this.env.renderString(templateText, preparedData, (err, res) => {
        if (err) reject(err);
        else resolve(res as string);
      });
    });
  }
  
  public async renderString(templateText: string, data: any): Promise<string> {
    return new Promise((resolve, reject) => {
      this.env.renderString(templateText, data, (err, res) => {
        if (err) reject(err);
        else resolve(res as string);
      });
    });
  }
}
