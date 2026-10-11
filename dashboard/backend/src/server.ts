/** Local development entry point: a plain Express server on PORT. */
import app from './app.js';

const port = Number(process.env.PORT ?? 3001);
app.listen(port, () => {
  console.log(`Dashboard API listening on http://localhost:${port}`);
});
