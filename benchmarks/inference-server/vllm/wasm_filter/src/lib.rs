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

    fn generate_weighted_random_bit(&mut self, p: f64) -> u8 {
        // Ensure p is between 0 and 1
        assert!(p >= 0.0 && p <= 1.0, "Probability must be between 0 and 1");

        // Generate a random number between 0 and 1
        let random_value = self.rng.next_u32() as f64 / u32::MAX as f64;

        // Return 0 with probability p, and 1 with probability 1 - p
        if random_value < p {
            0
        } else {
            1
        }
    }
}

impl Context for MyWasmFilter {}

impl HttpContext for MyWasmFilter {
    fn on_http_request_headers(&mut self, _: usize, _: bool) -> Action {
        // Check for the 'service' header
        if let Some(service_header) = self.get_http_request_header("service") {
            match service_header.as_str() {
                "prompt" => {
                    // Check for the 'prompt' and 'max_tokens' headers
                    if let Some(input_tokens_header) = self.get_http_request_header("input_tokens") {
                        if let Some(max_tokens_header) = self.get_http_request_header("max_tokens") {
                            if let Ok(max_tokens) = max_tokens_header.parse::<usize>() {
                                if let Ok(input_tokens) = input_tokens_header.parse::<usize>() {
                                    let total_count = input_tokens + max_tokens;
                                    let threshold = 200; // Define your combined word count and max_tokens threshold here
                                    let route = if total_count < threshold {
                                        "deployment-1"
                                    } else {
                                        "deployment-2"
                                    };
                                    self.set_http_request_header("x-route-to", Some(route));
                                } else {
                                    self.send_http_response(400, vec![("content-type", "text/plain")], Some(b"Invalid input_tokens header"));
                                return Action::Pause;
                                }
                            } else {
                                self.send_http_response(400, vec![("content-type", "text/plain")], Some(b"Invalid max_tokens header"));
                                return Action::Pause;
                            }
                        } else {
                            self.send_http_response(400, vec![("content-type", "text/plain")], Some(b"Missing max_tokens header"));
                            return Action::Pause;
                        }
                    } else {
                        self.send_http_response(400, vec![("content-type", "text/plain")], Some(b"Missing input_tokens header"));
                        return Action::Pause;
                    }
                }
                "short" => {
                    // Route to deployment-1 if service: short
                    self.set_http_request_header("x-route-to", Some("deployment-1"));
                }
                "long" => {
                    // Route to deployment-2 if service: long
                    self.set_http_request_header("x-route-to", Some("deployment-2"));
                }
                "random" => {
                    FILTER_INSTANCE.with(|filter| {
                        let mut filter = filter.borrow_mut();
                        let weighted_bit = filter.generate_weighted_random_bit(0.5); // Adjust the probability as needed
                        if weighted_bit == 0 {
                            self.set_http_request_header("x-route-to", Some("deployment-1"));
                        } else {
                            self.set_http_request_header("x-route-to", Some("deployment-2"));
                        }
                    });
                }
                _ => {
                    // Return error status code if service header has an unexpected value
                    self.send_http_response(400, vec![("content-type", "text/plain")], Some(b"Invalid service header"));
                    return Action::Pause;
                }
            }
        } else {
            // Return error status code if 'service' header is not present
            self.send_http_response(400, vec![("content-type", "text/plain")], Some(b"Missing service header"));
            return Action::Pause;
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
