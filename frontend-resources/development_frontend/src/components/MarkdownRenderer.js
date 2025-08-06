import React from 'react';

const MarkdownRenderer = ({ content }) => {
  // Split content into lines for processing
  const lines = content.split('\n');
  const elements = [];
  let i = 0;

  // Helper function to process inline markdown
  const processInlineMarkdown = (text) => {
    if (!text) return null;

    // Process in order: code, bold, italic, links
    const parts = [];
    let lastIndex = 0;
    
    // Combined regex for all inline elements
    const regex = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[([^\]]+)\]\(([^)]+)\))/g;
    let match;

    while ((match = regex.exec(text)) !== null) {
      // Add text before match
      if (match.index > lastIndex) {
        parts.push(text.substring(lastIndex, match.index));
      }

      if (match[1]) {
        // Inline code
        parts.push(
          <code key={parts.length} className="bg-gray-100 px-1 py-0.5 rounded text-sm font-mono">
            {match[1].slice(1, -1)}
          </code>
        );
      } else if (match[2]) {
        // Bold
        parts.push(
          <strong key={parts.length} className="font-semibold">
            {match[2].slice(2, -2)}
          </strong>
        );
      } else if (match[3]) {
        // Italic
        parts.push(
          <em key={parts.length} className="italic">
            {match[3].slice(1, -1)}
          </em>
        );
      } else if (match[4]) {
        // Link
        parts.push(
          <a
            key={parts.length}
            href={match[6]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 underline"
          >
            {match[5]}
          </a>
        );
      }

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  while (i < lines.length) {
    const line = lines[i];

    // Code blocks
    if (line.trim().startsWith('```')) {
      const codeLines = [];
      const language = line.trim().slice(3).trim();
      i++;
      
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      
      // Skip the closing ``` if it exists
      if (i < lines.length && lines[i].trim().startsWith('```')) {
        i++;
      }
      
      elements.push(
        <div key={`code-${elements.length}`} className="my-3">
          {language && (
            <div className="bg-gray-700 text-gray-300 text-xs px-3 py-1 rounded-t font-mono">
              {language}
            </div>
          )}
          <pre className={`bg-gray-800 text-gray-100 p-3 ${language ? 'rounded-b' : 'rounded'} overflow-x-auto`}>
            <code className="block">{codeLines.join('\n')}</code>
          </pre>
        </div>
      );
      continue;
    }

    // Headers
    if (line.startsWith('#')) {
      const level = line.match(/^#+/)[0].length;
      const text = line.slice(level).trim();
      const HeaderTag = `h${Math.min(level, 6)}`;
      const className = [
        'text-2xl font-bold mt-4 mb-2',
        'text-xl font-bold mt-3 mb-2',
        'text-lg font-semibold mt-2 mb-1',
        'text-base font-semibold mt-2 mb-1',
        'text-sm font-semibold mt-1 mb-1',
        'text-sm font-semibold mt-1 mb-1'
      ][level - 1];

      elements.push(
        <HeaderTag key={elements.length} className={className}>
          {processInlineMarkdown(text)}
        </HeaderTag>
      );
      i++;
      continue;
    }

    // Unordered lists
    if (line.trim().startsWith('- ') || line.trim().startsWith('* ')) {
      const listItems = [];
      const indent = line.search(/\S/);
      
      while (i < lines.length && (lines[i].trim().startsWith('- ') || lines[i].trim().startsWith('* '))) {
        const itemText = lines[i].trim().slice(2);
        listItems.push(
          <li key={listItems.length} className="ml-4">
            {processInlineMarkdown(itemText)}
          </li>
        );
        i++;
      }
      
      elements.push(
        <ul key={elements.length} className="list-disc list-inside my-2">
          {listItems}
        </ul>
      );
      continue;
    }

    // Ordered lists
    if (/^\d+\.\s/.test(line.trim())) {
      const listItems = [];
      
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        const itemText = lines[i].trim().replace(/^\d+\.\s/, '');
        listItems.push(
          <li key={listItems.length} className="ml-4">
            {processInlineMarkdown(itemText)}
          </li>
        );
        i++;
      }
      
      elements.push(
        <ol key={elements.length} className="list-decimal list-inside my-2">
          {listItems}
        </ol>
      );
      continue;
    }

    // Blockquotes
    if (line.startsWith('>')) {
      const quoteLines = [];
      
      while (i < lines.length && lines[i].startsWith('>')) {
        quoteLines.push(lines[i].slice(1).trim());
        i++;
      }
      
      elements.push(
        <blockquote key={elements.length} className="border-l-4 border-gray-300 pl-4 my-2 italic">
          {quoteLines.map((quoteLine, idx) => (
            <div key={idx}>{processInlineMarkdown(quoteLine)}</div>
          ))}
        </blockquote>
      );
      continue;
    }

    // Horizontal rule
    if (line.match(/^(-{3,}|_{3,}|\*{3,})$/)) {
      elements.push(
        <hr key={elements.length} className="my-4 border-gray-300" />
      );
      i++;
      continue;
    }

    // Empty lines
    if (line.trim() === '') {
      elements.push(<div key={elements.length} className="h-2" />);
      i++;
      continue;
    }

    // Regular paragraphs
    const paragraphLines = [];
    
    while (
      i < lines.length && 
      lines[i].trim() !== '' &&
      !lines[i].startsWith('#') &&
      !lines[i].startsWith('```') &&
      !lines[i].trim().startsWith('- ') &&
      !lines[i].trim().startsWith('* ') &&
      !/^\d+\.\s/.test(lines[i].trim()) &&
      !lines[i].startsWith('>') &&
      !lines[i].match(/^(-{3,}|_{3,}|\*{3,})$/)
    ) {
      paragraphLines.push(lines[i]);
      i++;
    }
    
    if (paragraphLines.length > 0) {
      elements.push(
        <p key={elements.length} className="my-2">
          {processInlineMarkdown(paragraphLines.join(' '))}
        </p>
      );
    }
  }

  return <div className="markdown-content">{elements}</div>;
};

export default MarkdownRenderer;