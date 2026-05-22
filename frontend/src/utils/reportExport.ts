import {
  Document,
  HeadingLevel,
  Packer,
  Paragraph,
  TextRun,
} from "docx";

const HEADING_LEVELS = {
  1: HeadingLevel.HEADING_1,
  2: HeadingLevel.HEADING_2,
  3: HeadingLevel.HEADING_3,
  4: HeadingLevel.HEADING_4,
  5: HeadingLevel.HEADING_5,
  6: HeadingLevel.HEADING_6,
} as const;

function buildTextRuns(content: string): TextRun[] {
  return [new TextRun(content)];
}

function buildParagraphs(markdown: string): Paragraph[] {
  const paragraphs: Paragraph[] = [];

  for (const line of markdown.split(/\r?\n/)) {
    const trimmed = line.trim();

    if (!trimmed) {
      paragraphs.push(new Paragraph({}));
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      const headingSize = Math.min(headingMatch[1].length, 6) as
        | 1
        | 2
        | 3
        | 4
        | 5
        | 6;

      paragraphs.push(
        new Paragraph({
          heading: HEADING_LEVELS[headingSize],
          children: buildTextRuns(headingMatch[2]),
        }),
      );
      continue;
    }

    const orderedListMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (orderedListMatch) {
      paragraphs.push(
        new Paragraph({
          children: buildTextRuns(orderedListMatch[1]),
          numbering: {
            reference: "report-numbering",
            level: 0,
          },
        }),
      );
      continue;
    }

    const bulletListMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (bulletListMatch) {
      paragraphs.push(
        new Paragraph({
          children: buildTextRuns(bulletListMatch[1]),
          bullet: {
            level: 0,
          },
        }),
      );
      continue;
    }

    paragraphs.push(
      new Paragraph({
        children: buildTextRuns(trimmed),
      }),
    );
  }

  return paragraphs;
}

export async function createReportDocxBlob(report: string): Promise<Blob> {
  const document = new Document({
    numbering: {
      config: [
        {
          reference: "report-numbering",
          levels: [
            {
              level: 0,
              format: "decimal",
              text: "%1.",
              alignment: "left",
            },
          ],
        },
      ],
    },
    sections: [
      {
        children: buildParagraphs(report),
      },
    ],
  });

  return Packer.toBlob(document);
}
