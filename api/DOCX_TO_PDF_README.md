# DOCX to PDF Azure Function

This Azure Function converts DOCX files to PDF using the `docx2pdf-converter` library.

## Prerequisites

### Local Development
- Node.js 18 or later
- npm

## Installation

```bash
cd api
npm install
```

## Usage

### API Endpoint

**POST** `/api/docx-to-pdf`

### Request

- **Content-Type**: `multipart/form-data`
- **Body**: Form data with a file field named `file` containing the DOCX file

### Response

- **Success (200)**: Returns PDF file
  - Content-Type: `application/pdf`
  - Content-Disposition: `attachment; filename="<filename>.pdf"`
- **Error (400)**: Invalid request
- **Error (500)**: Conversion failed

### Example using cURL

```bash
curl -X POST \
  -F "file=@/path/to/document.docx" \
  http://localhost:7071/api/docx-to-pdf \
  --output converted.pdf
```

### Example using JavaScript (fetch)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('http://localhost:7071/api/docx-to-pdf', {
  method: 'POST',
  body: formData
});

if (response.ok) {
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'converted.pdf';
  a.click();
}
```

### Example using Python

```python
import requests

with open('document.docx', 'rb') as f:
    files = {'file': f}
    response = requests.post('http://localhost:7071/api/docx-to-pdf', files=files)
    
    if response.status_code == 200:
        with open('converted.pdf', 'wb') as pdf_file:
            pdf_file.write(response.content)
```

## Running Locally

```bash
cd api
npm start
```

The function will be available at `http://localhost:7071/api/docx-to-pdf`

## Deploy to Azure

Deploy using Azure Functions Core Tools:

```bash
cd api
func azure functionapp publish <your-function-app-name>
```

Or using VS Code Azure Functions extension.

## Limitations

- Maximum file size is limited by Azure Functions request size limits (typically 100MB)
- Only `.docx` files are supported (not `.doc`)

## Error Handling

The function includes comprehensive error handling for:
- Invalid file format
- Missing file upload
- Conversion failures
- Timeout issues
- File system errors

All errors are logged and return appropriate HTTP status codes with JSON error messages.
