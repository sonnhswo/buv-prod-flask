const { app } = require('@azure/functions');
const { exec } = require('child_process');
const { promisify } = require('util');
const fs = require('fs').promises;
const path = require('path');
const os = require('os');
const multipart = require('parse-multipart-data');

const execAsync = promisify(exec);

app.http('docx-to-pdf', {
    methods: ['POST'],
    authLevel: 'anonymous',
    handler: async (request, context) => {
        context.log('DOCX to PDF conversion request received');

        try {
            // Get content type and check if it's multipart
            const contentType = request.headers.get('content-type');
            if (!contentType || !contentType.includes('multipart/form-data')) {
                return {
                    status: 400,
                    body: JSON.stringify({ error: 'Content-Type must be multipart/form-data' })
                };
            }

            // Parse the multipart data
            const boundary = contentType.split('boundary=')[1];
            const bodyBuffer = await request.arrayBuffer();
            const parts = multipart.parse(Buffer.from(bodyBuffer), boundary);

            if (!parts || parts.length === 0) {
                return {
                    status: 400,
                    body: JSON.stringify({ error: 'No file uploaded' })
                };
            }

            const filePart = parts.find(part => part.name === 'file');
            if (!filePart) {
                return {
                    status: 400,
                    body: JSON.stringify({ error: 'No file field found. Please upload file with field name "file"' })
                };
            }

            // Validate file extension
            const originalFilename = filePart.filename || 'document.docx';
            if (!originalFilename.toLowerCase().endsWith('.docx')) {
                return {
                    status: 400,
                    body: JSON.stringify({ error: 'Only .docx files are supported' })
                };
            }

            // Create temporary directory for processing
            const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), 'docx-to-pdf-'));
            const inputPath = path.join(tempDir, originalFilename);
            const outputDir = tempDir;

            try {
                // Write uploaded file to temp location
                await fs.writeFile(inputPath, filePart.data);
                context.log(`File saved to: ${inputPath}`);

                // Convert DOCX to PDF using LibreOffice
                // --headless: run without GUI
                // --convert-to pdf: convert to PDF format
                // --outdir: output directory
                const command = `libreoffice --headless --convert-to pdf --outdir "${outputDir}" "${inputPath}"`;
                context.log(`Executing: ${command}`);

                const { stdout, stderr } = await execAsync(command, {
                    timeout: 60000 // 60 second timeout
                });

                if (stderr) {
                    context.log(`LibreOffice stderr: ${stderr}`);
                }
                if (stdout) {
                    context.log(`LibreOffice stdout: ${stdout}`);
                }

                // Find the generated PDF file
                const pdfFilename = originalFilename.replace(/\.docx$/i, '.pdf');
                const pdfPath = path.join(outputDir, pdfFilename);

                // Check if PDF was created
                try {
                    await fs.access(pdfPath);
                } catch (error) {
                    context.log(`PDF not found at expected path: ${pdfPath}`);
                    return {
                        status: 500,
                        body: JSON.stringify({ error: 'PDF conversion failed - output file not found' })
                    };
                }

                // Read the PDF file
                const pdfBuffer = await fs.readFile(pdfPath);
                context.log(`PDF generated successfully, size: ${pdfBuffer.length} bytes`);

                // Clean up temp files
                await fs.unlink(inputPath).catch(err => context.log(`Error deleting input file: ${err.message}`));
                await fs.unlink(pdfPath).catch(err => context.log(`Error deleting output file: ${err.message}`));
                await fs.rmdir(tempDir).catch(err => context.log(`Error deleting temp dir: ${err.message}`));

                // Return the PDF
                return {
                    status: 200,
                    headers: {
                        'Content-Type': 'application/pdf',
                        'Content-Disposition': `attachment; filename="${pdfFilename}"`
                    },
                    body: pdfBuffer
                };

            } catch (conversionError) {
                // Clean up temp directory on error
                await fs.rm(tempDir, { recursive: true, force: true }).catch(err =>
                    context.log(`Error cleaning up temp dir: ${err.message}`)
                );
                throw conversionError;
            }

        } catch (error) {
            context.log(`Error: ${error.message}`);
            context.log(`Stack: ${error.stack}`);
            return {
                status: 500,
                body: JSON.stringify({
                    error: 'Internal server error',
                    message: error.message
                })
            };
        }
    }
});
