use proxy_wasm::traits::*;
use proxy_wasm::types::*;
use rand_core::RngCore;
use rand_core::SeedableRng;
use rand_pcg::Pcg32;
use std::cell::RefCell;
use std::rc::Rc;

thread_local! {
    static FILTER_INSTANCE: Rc<RefCell<MyWasmFilter>> = Rc::new(RefCell::new(MyWasmFilter::new()));
}

struct MyWasmFilter {
    rng: Pcg32,
}

impl MyWasmFilter {
    fn new() -> Self {
        MyWasmFilter {
            rng: Pcg32::seed_from_u64(42),
        }
    }

    fn generate_weighted_random_value(&mut self) -> u8 {
        // Generate a random number between 0 and 1
        let random_value = self.rng.next_u32() as f64 / u32::MAX as f64;

        // Return 1 with probability 1/3, 2 with probability 1/3, and 3 with probability 1/3
        if random_value < 1.0 / 3.0 {
            1
        } else if random_value < 2.0 / 3.0 {
            2
        } else {
            3
        }
    }

    fn get_random_deployment(&mut self) -> &'static str {
        match self.generate_weighted_random_value() {
            1 => "deployment-1",
            2 => "deployment-2",
            _ => "deployment-3",
        }
    }
}

impl Context for MyWasmFilter {}

impl HttpContext for MyWasmFilter {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Check for the 'lora' header
        if let Some(lora_header) = self.get_http_request_header("lora") {
            if lora_header == "sql-tuned" {
                // Route to deployment-1 if lora: sql_tuned
                self.set_http_request_header("x-route-to", Some("deployment-2"));
            } 
            else if lora_header == "tweet-summary" {
                // Route to deployment-1 if lora: sql_tuned
                self.set_http_request_header("x-route-to", Some("deployment-3"));
            }
            else {
                // Route to deployment-2 if lora header exists but is not 'sql_tuned'
                FILTER_INSTANCE.with(|filter| {
                    let mut filter = filter.borrow_mut();
                    let route = filter.get_random_deployment();
                    self.set_http_request_header("x-route-to", Some(route));
                });
            }
        } else {
            // Route to deployment-2 if 'lora' header is not present
            FILTER_INSTANCE.with(|filter| {
                let mut filter = filter.borrow_mut();
                let route = filter.get_random_deployment();
                self.set_http_request_header("x-route-to", Some(route));
            });
        }
        Action::Continue
    }
}

impl RootContext for MyWasmFilter {
    fn on_configure(&mut self, _: usize) -> bool {
        true
    }

    fn create_http_context(&self, _: u32) -> Option<Box<dyn HttpContext>> {
        Some(Box::new(MyWasmFilter::new()))
    }

    fn get_type(&self) -> Option<ContextType> {
        Some(ContextType::HttpContext)
    }
}

#[no_mangle]
pub fn _start() {
    proxy_wasm::set_log_level(LogLevel::Trace);
    proxy_wasm::set_root_context(|_| Box::new(MyWasmFilter::new()));
}
